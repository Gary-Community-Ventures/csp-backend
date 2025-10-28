from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import sentry_sdk
from clerk_backend_api import Clerk, CreateInvitationRequestBody
from flask import Blueprint, abort, current_app, jsonify, request

from app.auth.decorators import (
    ClerkUserType,
    api_key_required,
    auth_optional,
    auth_required,
)
from app.auth.helpers import get_current_user, get_family_user, get_provider_user
from app.constants import MAX_CHILDREN_PER_PROVIDER, UNKNOWN
from app.extensions import db
from app.models.attendance import Attendance
from app.models.family_invitation import FamilyInvitation
from app.models.family_payment_settings import FamilyPaymentSettings
from app.models.provider_invitation import ProviderInvitation
from app.models.provider_payment_settings import ProviderPaymentSettings
from app.services.allocation_service import AllocationService
from app.supabase.columns import Language
from app.supabase.helpers import cols, format_name, unwrap_or_abort
from app.supabase.tables import Child, Family, Guardian, Provider, ProviderChildMapping
from app.utils.date_utils import get_current_month_start, get_next_month_start
from app.utils.email.config import get_from_email_external
from app.utils.email.core import send_email
from app.utils.email.senders import (
    send_provider_invite_accept_email,
    send_provider_invited_email,
)
from app.utils.email.templates import InvitationTemplate
from app.utils.sms_service import send_sms

bp = Blueprint("family", __name__)


@bp.post("/family")
@api_key_required
def new_family():
    """
    DEPRECATED: Use POST /family/onboard instead.

    This endpoint creates a Clerk invitation and onboards a family.
    It is being phased out in favor of the new flow where users create
    their own Clerk accounts first, then get linked via /family/onboard.

    Will be removed in a future version.
    """
    current_app.logger.warning("DEPRECATED: POST /family endpoint called. Use POST /family/onboard instead.")

    data = request.json

    family_id = data.get("family_id")
    email = data.get("email")

    # Validate required fields
    if "family_id" not in data:
        abort(400, description="Missing required fields: family_id")

    if "email" not in data:
        abort(400, description="Missing required field: email")

    family_result = Family.select_by_id(
        cols(
            Family.LINK_ID,
            Child.join(
                Child.ID,
                Child.PAYMENT_ENABLED,
                Provider.join(Provider.ID),
            ),
        ),
        int(family_id),
    ).execute()
    family = unwrap_or_abort(family_result)
    children = Child.unwrap(family)

    # Send clerk invite first - this provides idempotency since Clerk will error on duplicate invites
    # This prevents allocations from being created multiple times if this endpoint is called multiple times
    clerk: Clerk = current_app.clerk_client
    fe_domain = current_app.config.get("FRONTEND_DOMAIN")
    meta_data = {
        "types": [ClerkUserType.FAMILY],  # NOTE: list in case we need to have people who fit into multiple categories
        "family_id": family_id,
    }

    clerk.invitations.create(
        request=CreateInvitationRequestBody(
            email_address=email,
            redirect_url=f"{fe_domain}/auth/sign-up",
            public_metadata=meta_data,
        )
    )

    # Create Chek user and FamilyPaymentSettings (idempotent - returns existing if already created)
    from app.utils.onboarding import onboard_family_to_chek

    onboard_family_to_chek(family_id)

    link_id = Family.LINK_ID(family)
    if link_id is None:
        return jsonify(data)

    invite: FamilyInvitation = FamilyInvitation.invitation_by_id(link_id).first()
    if invite is None:
        current_app.logger.warning(f"Family invitation with ID {link_id} not found.")
        return jsonify(data)

    provider_result = Provider.select_by_id(
        cols(Provider.ID, Child.join(Child.ID)), int(invite.provider_supabase_id)
    ).execute()
    provider = unwrap_or_abort(provider_result)
    if not provider:
        current_app.logger.warning(f"Provider with ID {invite.provider_supabase_id} not found.")
        return jsonify(data)

    extra_slots = MAX_CHILDREN_PER_PROVIDER - len(Child.unwrap(provider))

    for child in children:
        if extra_slots <= 0:
            break

        for provider in Provider.unwrap(child):
            if Provider.ID(provider) == invite.provider_supabase_id:
                continue

        ProviderChildMapping.query().insert(
            {
                ProviderChildMapping.CHILD_ID: Child.ID(child),
                ProviderChildMapping.PROVIDER_ID: invite.provider_supabase_id,
            }
        ).execute()

    invite.record_accepted()
    db.session.add(invite)
    db.session.commit()

    # Create allocations for current and next month (at the end after all other operations succeed)
    from app.utils.onboarding import (
        create_family_allocations,
        validate_family_allocations,
    )

    current_month_result, next_month_result = create_family_allocations(children, family_id)
    validate_family_allocations(children, family_id, current_month_result, next_month_result)

    return jsonify(data)


@bp.post("/family/onboard")
@api_key_required
def onboard_family():
    """
    Onboard an existing Clerk user to a family account.

    This endpoint:
    1. Links a Clerk user to a family in the database
    2. Updates Clerk metadata with family_id
    3. Onboards family to Chek payment system
    4. Creates monthly allocations
    5. Sends portal invitation email

    Idempotent: Safe to call multiple times. Uses Redis locking to prevent
    duplicate operations from concurrent requests.
    """
    data = request.json
    clerk_user_id = data.get("clerk_user_id")
    family_id = data.get("family_id")

    # Validate required fields
    if not clerk_user_id:
        abort(400, description="Missing required field: clerk_user_id")
    if not family_id:
        abort(400, description="Missing required field: family_id")

    # Get Redis connection for distributed locking
    try:
        redis_conn = current_app.extensions["job_manager"].get_redis()
        lock_key = f"onboarding:family:{family_id}"

        # Try to acquire lock (5 minute TTL) - fail-closed approach
        lock_acquired = redis_conn.set(lock_key, clerk_user_id, nx=True, ex=300)

        if not lock_acquired:
            # Another request is already processing or recently processed this
            current_app.logger.info(f"Family {family_id} onboarding already in progress or completed, skipping")
            return jsonify({"message": "Onboarding already in progress or completed"}), 200

    except Exception as redis_error:
        # Redis is down - fail closed (reject request)
        current_app.logger.error(f"Redis unavailable for onboarding lock: {redis_error}")
        sentry_sdk.capture_exception(redis_error)
        abort(503, description="Service temporarily unavailable, please retry in a few moments")

    try:
        # 1. Fetch family data with children and language preference
        family_result = Family.select_by_id(
            cols(
                Family.ID,
                Family.CLERK_USER_ID,
                Family.LANGUAGE,
                Family.PORTAL_INVITE_SENT_AT,
                Child.join(Child.ID, Child.PAYMENT_ENABLED),
                Guardian.join(Guardian.EMAIL, Guardian.TYPE),
            ),
            int(family_id),
        ).execute()
        family_data = unwrap_or_abort(family_result)
        children = Child.unwrap(family_data)
        guardians = Guardian.unwrap(family_data)

        # Validate that the clerk_user_id matches what's in the database
        stored_clerk_user_id = Family.CLERK_USER_ID(family_data)
        if stored_clerk_user_id and stored_clerk_user_id != clerk_user_id:
            current_app.logger.error(
                f"Clerk user ID mismatch for family {family_id}: "
                f"provided {clerk_user_id}, stored {stored_clerk_user_id}"
            )
            abort(400, description="Clerk user ID does not match family record")

        if not stored_clerk_user_id:
            current_app.logger.error(f"No clerk_user_id found in database for family {family_id}")
            abort(400, description="Family does not have a clerk_user_id set")

        # Get primary guardian email for portal invite
        primary_guardian = Guardian.get_primary_guardian(guardians)
        guardian_email = Guardian.EMAIL(primary_guardian) if primary_guardian else None

        if not guardian_email:
            current_app.logger.error(f"No primary guardian email found for family {family_id}")
            abort(400, description="Family has no primary guardian email")

        # 2. Update Clerk user metadata
        try:
            from app.utils.onboarding import update_clerk_user_metadata

            update_clerk_user_metadata(clerk_user_id, ClerkUserType.FAMILY, int(family_id))
        except Exception as clerk_error:
            current_app.logger.error(f"Failed to update Clerk user metadata: {clerk_error}")
            sentry_sdk.capture_exception(clerk_error)
            raise

        # 3. Onboard to Chek (already idempotent)
        from app.utils.onboarding import (
            create_family_allocations,
            onboard_family_to_chek,
        )

        onboard_family_to_chek(family_id)

        # 4. Create allocations for payment-enabled children (already idempotent via get_or_create)
        from app.utils.onboarding import validate_family_allocations

        current_month_result, next_month_result = create_family_allocations(children, family_id)
        validate_family_allocations(children, family_id, current_month_result, next_month_result)

        # 5. Send portal invite email (only once)
        if not Family.PORTAL_INVITE_SENT_AT(family_data):
            language = Family.LANGUAGE(family_data) or Language.ENGLISH

            from app.utils.onboarding import send_portal_invite_email

            email_sent = send_portal_invite_email(
                email=guardian_email,
                entity_type="family",
                entity_id=int(family_id),
                language=language,
                clerk_user_id=clerk_user_id,
            )

            if email_sent:
                # Mark portal invite as sent
                Family.query().update({"portal_invite_sent_at": datetime.now(timezone.utc)}).eq(
                    "id", family_id
                ).execute()
                current_app.logger.info(f"Sent portal invite email to family {family_id}")
            else:
                current_app.logger.error(f"Failed to send portal invite email to family {family_id}")
        else:
            current_app.logger.info(f"Portal invite already sent for family {family_id}, skipping email")

        return (
            jsonify(
                {
                    "message": "Family onboarded successfully",
                    "family_id": family_id,
                    "clerk_user_id": clerk_user_id,
                }
            ),
            200,
        )

    except Exception as e:
        current_app.logger.error(f"Error onboarding family {family_id}: {e}")
        sentry_sdk.capture_exception(e)
        raise

    finally:
        # Always release the lock
        try:
            redis_conn.delete(lock_key)
        except Exception as cleanup_error:
            current_app.logger.warning(f"Failed to release Redis lock: {cleanup_error}")


@bp.get("/family/default_child_id")
@auth_required(ClerkUserType.FAMILY)
def default_child_id():
    user = get_family_user()
    family_id = user.user_data.family_id

    children_result = Child.select_by_family_id(cols(Child.ID), int(family_id)).execute()
    children_data = unwrap_or_abort(children_result)

    if not children_data or len(children_data) == 0:
        abort(404, description="No children found for this family.")

    active_child_id = Child.ID(children_data[0])

    return jsonify({"child_id": active_child_id})


@bp.get("/family/")
@bp.get("/family/<child_id>")
@auth_required(ClerkUserType.FAMILY)
def family_data(child_id: Optional[str] = None):
    user = get_family_user()
    family_id = user.user_data.family_id

    family_children_result = Child.select_by_family_id(
        cols(
            Child.ID,
            Child.FIRST_NAME,
            Child.LAST_NAME,
            Child.MONTHLY_ALLOCATION,
            Child.PRORATED_ALLOCATION,
            Child.STATUS,
            Child.PAYMENT_ENABLED,
            Provider.join(Provider.ID, Provider.NAME, Provider.STATUS, Provider.TYPE, Provider.PAYMENT_ENABLED),
        ),
        int(family_id),
    ).execute()

    family_children = unwrap_or_abort(family_children_result)

    if not family_children or len(family_children) == 0:
        abort(404, description="No children found for this family.")

    # Determine the active child
    if child_id is not None:
        selected_child = None
        for child in family_children:
            if Child.ID(child) == child_id:
                selected_child = child
                break

        if selected_child is None:
            abort(404, description=f"Child with ID {child_id} not found.")

        child_data = selected_child
    else:
        child_data = family_children[0]

    provider_data = Provider.unwrap(child_data)

    selected_child_info = {
        "id": Child.ID(child_data),
        "first_name": Child.FIRST_NAME(child_data),
        "last_name": Child.LAST_NAME(child_data),
        "monthly_allocation": Child.MONTHLY_ALLOCATION(child_data),
        "prorated_first_month_allocation": Child.PRORATED_ALLOCATION(child_data),
        "is_payment_enabled": Child.PAYMENT_ENABLED(child_data),
    }

    providers = []
    for p in provider_data:
        provider_id = Provider.ID(p)

        attendance_is_overdue = (
            Attendance.filter_by_overdue_attendance(provider_id, child_id, Provider.TYPE(p)).count() > 0
        )

        # Look up the ProviderPaymentSettings to get is_payable status
        provider_payment_settings = ProviderPaymentSettings.query.filter_by(provider_supabase_id=provider_id).first()
        current_app.logger.error(f"Provider {provider_id} payment settings: {provider_payment_settings}")

        provider_status = Provider.STATUS(p)
        provider_type = Provider.TYPE(p)

        providers.append(
            {
                "id": provider_id,
                "name": Provider.NAME(p),
                "status": provider_status.lower() if provider_status else "pending",
                "type": provider_type.lower() if provider_type else "unlicensed",
                "is_payable": provider_payment_settings.is_payable if provider_payment_settings else False,
                "is_payment_enabled": Provider.PAYMENT_ENABLED(p),
                "attendance_is_overdue": attendance_is_overdue,
            }
        )

    children = [
        {
            "id": Child.ID(c),
            "first_name": Child.FIRST_NAME(c),
            "last_name": Child.LAST_NAME(c),
        }
        for c in family_children
    ]

    notifications = []
    child_status = Child.STATUS(child_data)
    if child_status and child_status.lower() == "pending":
        notifications.append({"type": "application_pending"})
    elif child_status and child_status.lower() == "denied":
        notifications.append({"type": "application_denied"})

    child_ids = [Child.ID(c) for c in family_children]
    attendance_due = Attendance.filter_by_child_ids(child_ids).count() > 0
    if attendance_due:
        notifications.append({"type": "attendance"})

    family_payment_settings = FamilyPaymentSettings.query.filter_by(family_supabase_id=family_id).first()

    return jsonify(
        {
            "selected_child_info": selected_child_info,
            "providers": providers,
            "children": children,
            "notifications": notifications,
            "is_also_provider": ClerkUserType.PROVIDER.value in user.user_data.types,
            "can_make_payments": family_payment_settings.can_make_payments if family_payment_settings else False,
            "attendance_due": attendance_due,
        }
    )


@dataclass
class InviteProviderMessage:
    subject: str
    email: str
    sms: str


def get_invite_provider_message(lang: str, family_name: str, child_name: str, link: str):
    language = Language.SPANISH if lang == "es" else Language.ENGLISH
    email_html = InvitationTemplate.get_provider_invitation_content(family_name, child_name, link, language)

    if lang == "es":
        return InviteProviderMessage(
            subject=f"¡{family_name} se complace en invitarte al programa CAP para cuidar a {child_name}!",
            email=email_html,
            sms=f"¡{family_name} te invitó a unirte al programa piloto de accesibilidad al cuidado infantil (CAP) para cuidar a {child_name}! CAP ayuda a las familias a pagar a proveedores como tú. ¡Toca para obtener más información y postularte! {link} ¿Preguntas? support@capcolorado.org.",
        )

    return InviteProviderMessage(
        subject=f"{family_name} is excited to invite you to the CAP program to care for {child_name}!",
        email=email_html,
        sms=f"{family_name} invited you to join the Childcare Affordability Pilot (CAP) to provide care for {child_name}! CAP can help families pay providers like you. Tap to learn more and apply! {link} Questions? support@capcolorado.org.",
    )


@bp.post("/family/invite-provider")
@auth_required(ClerkUserType.FAMILY)
def invite_provider():
    data = request.json

    if "provider_email" not in data:
        abort(400, description="Missing required field: provider_email")
    if "provider_cell" not in data:
        abort(400, description="Missing required field: provider_cell")
    if "child_ids" not in data:
        abort(400, description="Missing required field: child_ids")
    if type(data["child_ids"]) != list:
        abort(400, description="child_ids must be a list of child IDs")
    if len(data["child_ids"]) == 0:
        abort(400, description="child_ids must not be empty")

    if "lang" not in data:
        data["lang"] = "en"

    user = get_family_user()
    family_id = user.user_data.family_id

    family_result = Family.select_by_id(
        cols(
            Family.ID,
            Guardian.join(Guardian.FIRST_NAME, Guardian.LAST_NAME, Guardian.TYPE),
            Child.join(Child.ID, Child.FIRST_NAME, Child.LAST_NAME),
        ),
        int(family_id),
    ).execute()

    family_data = unwrap_or_abort(family_result)
    if not family_data:
        abort(404, description=f"Family with ID {family_id} not found.")

    guardians = Guardian.unwrap(family_data)
    primary_guardian = Guardian.get_primary_guardian(guardians)

    family_children = Child.unwrap(family_data)

    # Validate requested children belong to family
    children = []
    for child_id in data["child_ids"]:
        child = None
        for family_child in family_children:
            if Child.ID(family_child) == child_id:
                child = family_child
                break

        if child is None:
            abort(404, description=f"Child with ID {child_id} not found.")

        children.append(child)

    family_name = format_name(primary_guardian)

    invitations: list[ProviderInvitation] = []
    for child in children:
        try:
            child_id = Child.ID(child)
            id = str(uuid4())

            invitation = ProviderInvitation.new(id, data["provider_email"], child_id)
            db.session.add(invitation)
            invitations.append(invitation)

            domain = current_app.config.get("FRONTEND_DOMAIN")
            link = f"{domain}/invite/provider/{id}"

            child_name = format_name(child)

            message = get_invite_provider_message(
                data["lang"],
                family_name,
                child_name,
                link,
            )

            from_email = get_from_email_external()
            email_sent = send_email(
                from_email,
                data["provider_email"],
                message.subject,
                message.email,
                email_type="family_provider_invitation",
                context_data={
                    "family_name": family_name,
                    "family_id": str(family_id),
                    "provider_email": data["provider_email"],
                    "invitation_ids": [str(i.public_id) for i in invitations],
                },
                is_internal=False,
            )
            if email_sent:
                invitation.record_email_sent()

            if data["provider_cell"] is not None:
                sms_sent = send_sms(data["provider_cell"], message.sms, data["lang"])
                if sms_sent:
                    invitation.record_sms_sent()

        except Exception as e:
            current_app.logger.error(f"Failed to send provider invite for child ID {child_id}: {e}")
        finally:
            db.session.commit()

    send_provider_invited_email(family_name, family_id, data["provider_email"], [i.public_id for i in invitations])

    return jsonify({"message": "Success"}, 201)


@dataclass
class InviteData:
    child_data: dict
    family_data: dict
    guardian_data: dict  # Primary guardian data
    current_child_count: int
    already_caring_for: bool = False
    at_max_child_count: bool = False


def get_invite_data(child_id: str, provider_id: Optional[str] = None):
    current_child_count = 0
    already_caring_for = False

    child_result = Child.select_by_id(
        cols(
            Child.ID,
            Child.FIRST_NAME,
            Child.LAST_NAME,
            Child.FAMILY_ID,
            Family.join(
                Family.ID,
                Guardian.join(
                    Guardian.FIRST_NAME, Guardian.LAST_NAME, Guardian.EMAIL, Guardian.PHONE_NUMBER, Guardian.TYPE
                ),
            ),
            Provider.join(Provider.ID, Child.join(Child.ID)),
        ),
        int(child_id),
    ).execute()
    child_data = unwrap_or_abort(child_result)

    if child_data is None:
        abort(404, description=f"Child with ID {child_id} not found.")

    family_data = Family.unwrap(child_data)

    guardians = Guardian.unwrap(family_data)
    primary_guardian = Guardian.get_primary_guardian(guardians)

    # Check if provider already has this child and count their total children
    if provider_id is not None:
        child_providers = Provider.unwrap(child_data)
        for provider in child_providers:
            if Provider.ID(provider) == provider_id:
                already_caring_for = True
                # Count all children this provider cares for
                provider_children = Child.unwrap(provider)
                current_child_count = len(provider_children)
                break

    invite_data = InviteData(
        child_data=child_data,
        family_data=family_data,
        guardian_data=primary_guardian,
        current_child_count=current_child_count,
        already_caring_for=already_caring_for,
        at_max_child_count=(current_child_count >= MAX_CHILDREN_PER_PROVIDER),
    )

    return invite_data


@bp.get("/family/provider-invite/<invite_id>")
@auth_optional
def provider_invite(invite_id: str):
    invitation_query = ProviderInvitation.invitations_by_id(invite_id)
    invitation = invitation_query.first()

    if invitation is None:
        abort(404, description=f"Family invitation with ID {invite_id} not found.")

    invitation.record_opened()
    db.session.add(invitation)
    db.session.commit()

    user = get_current_user()
    if user is not None and user.user_data.provider_id is not None:
        invite_data = get_invite_data(invitation.child_supabase_id, user.user_data.provider_id)
    else:
        invite_data = get_invite_data(invitation.child_supabase_id)

    child = {
        "id": Child.ID(invite_data.child_data),
        "first_name": Child.FIRST_NAME(invite_data.child_data),
        "last_name": Child.LAST_NAME(invite_data.child_data),
    }

    family = {
        "id": Family.ID(invite_data.family_data),
        "first_name": Guardian.FIRST_NAME(invite_data.guardian_data) if invite_data.guardian_data else UNKNOWN,
        "last_name": Guardian.LAST_NAME(invite_data.guardian_data) if invite_data.guardian_data else UNKNOWN,
    }

    return jsonify(
        {
            "accepted": invitation.accepted,
            "child": child,
            "family": family,
            "already_caring_for": invite_data.already_caring_for,
            "at_max_child_count": invite_data.at_max_child_count,
        }
    )


@bp.post("/family/provider-invite/<invite_id>/accept")
@auth_required(ClerkUserType.PROVIDER)
def accept_provider_invite(invite_id: str):
    user = get_provider_user()

    invitation_query = ProviderInvitation.invitations_by_id(invite_id)
    invitation = invitation_query.first()

    if invitation.accepted:
        abort(400, description="Invitation already accepted.")

    invite_data = get_invite_data(invitation.child_supabase_id, user.user_data.provider_id)

    provider_result = Provider.select_by_id(cols(Provider.ID, Provider.NAME), int(user.user_data.provider_id)).execute()

    provider = unwrap_or_abort(provider_result)
    if not provider:
        abort(404, description=f"Provider with ID {user.user_data.provider_id} not found.")

    if invite_data.at_max_child_count:
        abort(400, description=f"Provider cannot have more than {MAX_CHILDREN_PER_PROVIDER} children.")

    if invite_data.already_caring_for:
        abort(400, description=f"Provider already has a child in the family.")

    parent_name = format_name(invite_data.guardian_data)
    child_name = format_name(invite_data.child_data)

    accept_request = send_provider_invite_accept_email(
        provider_name=Provider.NAME(provider),
        provider_id=Provider.ID(provider),
        parent_name=parent_name,
        parent_id=Family.ID(invite_data.family_data),
        child_name=child_name,
        child_id=Child.ID(invite_data.child_data),
    )

    if not accept_request:
        current_app.logger.error(
            f"Failed to send provider invite accept email for provider ID {user.user_data.provider_id} and family ID {Family.ID(invite_data.family_data)}.",
        )

    invitation.record_accepted()
    db.session.add(invitation)
    db.session.commit()

    return jsonify({"message": "Success"}, 200)
