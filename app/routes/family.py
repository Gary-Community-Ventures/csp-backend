from dataclasses import dataclass
from typing import Optional
from uuid import uuid4

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
from app.models.family_payment_settings import FamilyPaymentSettings
from app.models.provider_invitation import ProviderInvitation
from app.models.provider_payment_settings import ProviderPaymentSettings
from app.services.allocation_service import AllocationService
from app.supabase.helpers import cols, format_name, unwrap_or_abort
from app.supabase.tables import Child, Family, Guardian, Provider
from app.utils.date_utils import get_current_month_start, get_next_month_start
from app.utils.email_service import (
    get_from_email_internal,
    html_link,
    send_email,
    send_provider_invite_accept_email,
    send_provider_invited_email,
)
from app.utils.sms_service import send_sms

bp = Blueprint("family", __name__)


def create_allocations(family_children, month) -> None:
    """Create allocations for a list of children for a specific month.

    Args:
        family_children: List of child data from Supabase query
        month: The month to create allocations for
    """
    child_ids = [Child.ID(child) for child in family_children]
    allocation_service = AllocationService(current_app)
    allocation_service.create_allocations_for_specific_children(child_ids, month)


@bp.post("/family")
@api_key_required
def new_family():
    data = request.json

    family_id = data.get("family_id")
    email = data.get("email")

    # Validate required fields
    if "family_id" not in data:
        abort(400, description="Missing required fields: family_id")

    if "email" not in data:
        abort(400, description="Missing required field: email")

    family_children_result = Child.select_by_family_id(cols(Child.ID), int(family_id)).execute()
    family_children = unwrap_or_abort(family_children_result)

    # Create Chek user and FamilyPaymentSettings
    payment_service = current_app.payment_service
    family_settings = payment_service.onboard_family(family_external_id=family_id)
    current_app.logger.info(
        f"Created FamilyPaymentSettings for family {family_id} with Chek user {family_settings.chek_user_id}"
    )

    # Create allocations for current and next month
    create_allocations(family_children, get_current_month_start())
    create_allocations(family_children, get_next_month_start())
    db.session.commit()

    # send clerk invite
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

    return jsonify(data)


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
        # Look up the ProviderPaymentSettings to get is_payable status
        provider_payment_settings = ProviderPaymentSettings.query.filter_by(provider_external_id=provider_id).first()
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
    needs_attendance = Attendance.filter_by_child_ids(child_ids).count() > 0
    if needs_attendance:
        notifications.append({"type": "attendance"})

    family_payment_settings = FamilyPaymentSettings.query.filter_by(family_external_id=family_id).first()

    return jsonify(
        {
            "selected_child_info": selected_child_info,
            "providers": providers,
            "children": children,
            "notifications": notifications,
            "is_also_provider": ClerkUserType.PROVIDER.value in user.user_data.types,
            "can_make_payments": family_payment_settings.can_make_payments if family_payment_settings else False,
        }
    )


@dataclass
class InviteProviderMessage:
    subject: str
    email: str
    sms: str


def get_invite_provider_message(lang: str, family_name: str, child_name: str, link: str):
    if lang == "es":
        return InviteProviderMessage(
            subject=f"¡{family_name} se complace en invitarte al programa CAP para cuidar a {child_name}!",
            email=f'<html><body>¡{family_name} lo ha invitado a unirse al programa piloto Childcare Affordability Pilot (CAP) como proveedor de {child_name}, ¡Y nos encantaría tenerte a bordo!<br><br>CAP es un programa de 9 meses que ayuda a las familias a pagar el cuidado infantil y a proveedores como usted a recibir su pago. Recibirá pagos de CAP, mantendrá sus rutinas de cuidado habituales y apoyará a las familias con las que ya trabaja, o a nuevas familias.<br><br>¡Haga clic {html_link(link, "aquí")} para aceptar la invitación y comenzar!<br><br>¿Tienes preguntas? Escríbenos a <a href="mailto:support@capcolorado.org" style="color: #0066cc; text-decoration: underline;">support@capcolorado.org</a></body></html>',
            sms=f"¡{family_name} te invitó a unirte al programa CAP para cuidar a {child_name}! CAP ayuda a las familias a pagar el cuidado infantil y a proveedores como tú a recibir su pago. Toque para aceptar: {link} ¿Preguntas? support@capcolorado.org.",
        )

    return InviteProviderMessage(
        subject=f"{family_name} is excited to invite you to the CAP program to care for {child_name}!",
        email=f'<html><body>{family_name} has invited you to join the Childcare Affordability Pilot (CAP) as a provider for {child_name}—and we’d love to have you on board!<br><br>CAP is a 9-month program that helps families pay for childcare and helps providers like you get paid. You’ll receive payments through CAP, keep your usual care routines, and support families you already work with—or new ones.<br><br>Click {html_link(link, "here")} to accept the invitation and get started!<br><br>Questions? Email us at <a href="mailto:support@capcolorado.org" style="color: #0066cc; text-decoration: underline;">support@capcolorado.org</a>.</body></html>',
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
            Guardian.join(Guardian.FIRST_NAME, Guardian.LAST_NAME, Guardian.IS_PRIMARY),
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

    family_name = format_name(primary_guardian) if primary_guardian else UNKNOWN

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

            from_email = get_from_email_internal()
            email_sent = send_email(from_email, data["provider_email"], message.subject, message.email)
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

    send_provider_invited_email(family_name, family_id, [i.public_id for i in invitations])

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
            Family.join(Family.ID),
            Guardian.join(
                Guardian.FIRST_NAME, Guardian.LAST_NAME, Guardian.EMAIL, Guardian.PHONE_NUMBER, Guardian.IS_PRIMARY
            ),
            Provider.join(Provider.ID, Child.join(Child.ID)),
        ),
        int(child_id),
    ).execute()

    child_data = unwrap_or_abort(child_result)
    if not child_data:
        abort(404, description=f"Child with ID {child_id} not found.")

    family_data = Family.unwrap(child_data)

    guardians = Guardian.unwrap(child_data)
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
        invite_data = get_invite_data(invitation.child_google_sheet_id, user.user_data.provider_id)
    else:
        invite_data = get_invite_data(invitation.child_google_sheet_id)

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

    invite_data = get_invite_data(invitation.child_google_sheet_id, user.user_data.provider_id)

    provider_result = Provider.select_by_id(cols(Provider.ID, Provider.NAME), int(user.user_data.provider_id)).execute()

    provider = unwrap_or_abort(provider_result)
    if not provider:
        abort(404, description=f"Provider with ID {user.user_data.provider_id} not found.")

    if invite_data.at_max_child_count:
        abort(400, description=f"Provider cannot have more than {MAX_CHILDREN_PER_PROVIDER} children.")

    if invite_data.already_caring_for:
        abort(400, description=f"Provider already has a child in the family.")

    parent_name = format_name(invite_data.guardian_data) if invite_data.guardian_data else UNKNOWN
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
