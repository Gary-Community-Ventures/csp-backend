from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from uuid import uuid4

from clerk_backend_api import Clerk, CreateInvitationRequestBody
from flask import Blueprint, abort, current_app, jsonify, request
from pydantic import ValidationError

from app.auth.decorators import (
    ClerkUserType,
    api_key_required,
    auth_optional,
    auth_required,
)
from app.auth.helpers import get_current_user, get_family_user, get_provider_user
from app.constants import CHEK_STATUS_STALE_MINUTES, MAX_CHILDREN_PER_PROVIDER
from app.enums.payment_method import PaymentMethod
from app.extensions import db
from app.models import AllocatedCareDay, MonthAllocation
from app.models.attendance import Attendance
from app.models.family_invitation import FamilyInvitation
from app.models.payment_rate import PaymentRate
from app.models.provider_invitation import ProviderInvitation
from app.models.provider_payment_settings import ProviderPaymentSettings
from app.schemas.payment import PaymentInitializationResponse
from app.schemas.provider_payment import (
    PaymentMethodInitializeRequest,
    PaymentMethodUpdateRequest,
    PaymentMethodUpdateResponse,
    PaymentSettingsResponse,
)
from app.supabase.columns import Language
from app.supabase.helpers import UnwrapError, cols, format_name, unwrap_or_abort
from app.supabase.tables import Child, Family, Guardian, Provider, ProviderChildMapping
from app.utils.email.config import get_from_email_external
from app.utils.email.core import send_email
from app.utils.email.senders import (
    send_family_invite_accept_email,
    send_family_invited_email,
)
from app.utils.email.templates import InvitationTemplate
from app.utils.sms_service import send_sms

bp = Blueprint("provider", __name__)


@bp.post("/provider")
@api_key_required
def new_provider():
    data = request.json

    # Validate required fields
    if "provider_id" not in data:
        abort(400, description="Missing required fields: provider_id")

    if "email" not in data:
        abort(400, description="Missing required field: email")

    provider_id = data["provider_id"]

    provider_result = Provider.select_by_id(cols(Provider.LINK_ID, Child.join(Child.ID)), int(provider_id)).execute()
    provider = unwrap_or_abort(provider_result)
    if provider is None:
        abort(404, description=f"Provider with ID {provider_id} not found.")

    # Create Chek user and ProviderPaymentSettings
    payment_service = current_app.payment_service
    provider_settings = payment_service.onboard_provider(provider_id)
    current_app.logger.info(
        f"Created ProviderPaymentSettings for provider {provider_id} with Chek user {provider_settings.chek_user_id}"
    )

    # send clerk invite
    clerk: Clerk = current_app.clerk_client
    fe_domain = current_app.config.get("FRONTEND_DOMAIN")
    meta_data = {
        "types": [ClerkUserType.PROVIDER],  # NOTE: list in case we need to have people who fit into multiple categories
        "provider_id": provider_id,
    }

    clerk.invitations.create(
        request=CreateInvitationRequestBody(
            email_address=data["email"],
            redirect_url=f"{fe_domain}/auth/sign-up",
            public_metadata=meta_data,
        )
    )

    link_id = Provider.LINK_ID(provider)
    if link_id is None:
        return jsonify(data)

    invites: list[ProviderInvitation] = ProviderInvitation.invitations_by_id(link_id).all()
    if len(invites) == 0:
        current_app.logger.warning(f"Provider invitation with ID {link_id} not found.")
        return jsonify(data)

    for invite in invites[:MAX_CHILDREN_PER_PROVIDER]:
        child_result = Child.select_by_id(
            cols(Child.ID, Provider.join(Provider.ID)), int(invite.child_supabase_id)
        ).execute()
        child = unwrap_or_abort(child_result)

        if child is None:
            current_app.logger.warning(f"Child with ID {invite.child_supabase_id} not found.")
            continue

        if len(Provider.unwrap(child)) > 0:
            continue

        ProviderChildMapping.query().insert(
            {
                ProviderChildMapping.CHILD_ID: invite.child_supabase_id,
                ProviderChildMapping.PROVIDER_ID: provider_id,
            }
        ).execute()
        invite.record_accepted()
        db.session.add(invite)

    db.session.commit()

    return jsonify(data)


@bp.get("/provider")
@auth_required(ClerkUserType.PROVIDER)
def get_provider_data():
    user = get_provider_user()
    provider_id = user.user_data.provider_id

    provider_result = Provider.select_by_id(
        cols(
            Provider.ID,
            Provider.FIRST_NAME,
            Provider.LAST_NAME,
            Provider.PAYMENT_ENABLED,
            Provider.STATUS,
            Provider.TYPE,
            Provider.CPR_CERTIFIED,
            Provider.CPR_TRAINING_LINK,
            Child.join(Child.ID, Child.FIRST_NAME, Child.LAST_NAME),
        ),
        int(provider_id),
    ).execute()

    provider_data = unwrap_or_abort(provider_result)
    if not provider_data:
        abort(404, description=f"Provider with ID {provider_id} not found.")

    children_data = Child.unwrap(provider_data)

    provider_payment_settings = ProviderPaymentSettings.query.filter_by(provider_supabase_id=provider_id).first()

    # Can be "yes", "no", "I don't know" or None. Normalize to boolean or None for FE.
    cpr_certified = None
    if Provider.CPR_CERTIFIED(provider_data) is not None:
        cpr_certified = Provider.CPR_CERTIFIED(provider_data).lower() == "yes"

    provider_info = {
        "id": Provider.ID(provider_data),
        "first_name": Provider.FIRST_NAME(provider_data),
        "last_name": Provider.LAST_NAME(provider_data),
        "is_payment_enabled": Provider.PAYMENT_ENABLED(provider_data),
        "is_payable": provider_payment_settings.is_payable if provider_payment_settings else False,
        "type": Provider.TYPE(provider_data).lower(),
        "cpr_certified": cpr_certified,
        "cpr_training_link": Provider.CPR_TRAINING_LINK(provider_data),
    }

    children = []
    for child in children_data:
        child_id = Child.ID(child)
        payment_rate = PaymentRate.get(provider_id=provider_id, child_id=child_id)

        children.append(
            {
                "id": child_id,
                "first_name": Child.FIRST_NAME(child),
                "last_name": Child.LAST_NAME(child),
                "half_day_rate_cents": payment_rate.half_day_rate_cents if payment_rate is not None else None,
                "full_day_rate_cents": payment_rate.full_day_rate_cents if payment_rate is not None else None,
            }
        )

    notifications = []
    provider_status = Provider.STATUS(provider_data)
    if provider_status and provider_status.lower() == "pending":
        notifications.append({"type": "application_pending"})
    elif provider_status and provider_status.lower() == "denied":
        notifications.append({"type": "application_denied"})

    needs_attendance = Attendance.filter_by_provider_id(provider_id).count() > 0
    if needs_attendance:
        notifications.append({"type": "attendance"})

    return jsonify(
        {
            "provider_info": provider_info,
            "children": children,
            "curriculum": None,
            "notifications": notifications,
            "max_child_count": MAX_CHILDREN_PER_PROVIDER,
            "is_also_family": ClerkUserType.FAMILY.value in user.user_data.types,
        }
    )


@bp.get("/provider/payment-settings")
@auth_required(ClerkUserType.PROVIDER)
def get_payment_settings():
    """Get provider's payment settings including payment method and status."""
    user = get_provider_user()
    provider_id = user.user_data.provider_id

    # Get or create ProviderPaymentSettings record
    provider_payment_settings = ProviderPaymentSettings.query.filter_by(provider_supabase_id=provider_id).first()

    if not provider_payment_settings:
        # Onboard provider to Chek when first accessing payment settings
        try:
            payment_service = current_app.payment_service
            provider_payment_settings = payment_service.onboard_provider(provider_id)
            current_app.logger.info(f"Onboarded provider {provider_id} to Chek via payment-settings endpoint")
        except Exception as e:
            current_app.logger.error(f"Failed to onboard provider {provider_id} to Chek: {e}")
            # Return empty settings if onboarding fails
            error_response = PaymentSettingsResponse(
                provider_id=provider_id,
                chek_user_id=None,
                payment_method=None,
                payment_method_updated_at=None,
                is_payable=False,
                needs_refresh=False,
                last_sync=None,
                card={"available": False, "status": None, "id": None},
                ach={"available": False, "status": None, "id": None},
                validation={"is_valid": False, "message": "Onboarding to Chek failed"},
            )
            return error_response.model_dump_json(), 500, {"Content-Type": "application/json"}

    # Check if status is stale and needs refresh
    needs_refresh = False
    if provider_payment_settings.last_chek_sync_at:
        time_since_sync = datetime.now(timezone.utc) - provider_payment_settings.last_chek_sync_at
        if time_since_sync.total_seconds() > CHEK_STATUS_STALE_MINUTES * 60:
            needs_refresh = True

    payment_settings = PaymentSettingsResponse(
        provider_id=provider_id,
        chek_user_id=provider_payment_settings.chek_user_id,
        payment_method=(
            provider_payment_settings.payment_method.value if provider_payment_settings.payment_method else None
        ),
        payment_method_updated_at=(
            provider_payment_settings.payment_method_updated_at.isoformat()
            if provider_payment_settings.payment_method_updated_at
            else None
        ),
        is_payable=provider_payment_settings.is_payable,
        needs_refresh=needs_refresh,
        last_sync=(
            provider_payment_settings.last_chek_sync_at.isoformat()
            if provider_payment_settings.last_chek_sync_at
            else None
        ),
        card={
            "available": provider_payment_settings.chek_card_id is not None,
            "status": provider_payment_settings.chek_card_status,
            "id": provider_payment_settings.chek_card_id,
        },
        ach={
            "available": provider_payment_settings.chek_direct_pay_id is not None,
            "status": provider_payment_settings.chek_direct_pay_status,
            "id": provider_payment_settings.chek_direct_pay_id,
        },
        validation={
            "is_valid": provider_payment_settings.validate_payment_method_status()[0],
            "message": provider_payment_settings.validate_payment_method_status()[1],
        },
    )

    return payment_settings.model_dump_json(), 200, {"Content-Type": "application/json"}


@bp.put("/provider/payment-settings")
@auth_required(ClerkUserType.PROVIDER)
def update_payment_settings():
    """Update provider's payment method (switch between card and ACH)."""
    user = get_provider_user()
    provider_id = user.user_data.provider_id

    try:
        request_data = PaymentMethodUpdateRequest.model_validate(request.get_json())
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    # Validate payment method
    try:
        new_payment_method = PaymentMethod(request_data.payment_method)
    except ValueError:
        return jsonify({"error": f"Invalid payment method. Must be one of: {[e.value for e in PaymentMethod]}"}), 400

    # Get provider payment settings record
    existing_provider_payment_settings = ProviderPaymentSettings.query.filter_by(
        provider_supabase_id=provider_id
    ).first()

    if not existing_provider_payment_settings:
        abort(404, description="Provider payment settings not found. Please complete onboarding first.")

    # Check if the payment method is available
    if new_payment_method == PaymentMethod.CARD and not existing_provider_payment_settings.chek_card_id:
        abort(400, description="Virtual card not available. Please set up a virtual card first.")

    if new_payment_method == PaymentMethod.ACH and not existing_provider_payment_settings.chek_direct_pay_id:
        abort(400, description="ACH not available. Please set up ACH payment first.")

    # Update payment method
    old_payment_method = existing_provider_payment_settings.payment_method
    existing_provider_payment_settings.payment_method = new_payment_method
    existing_provider_payment_settings.payment_method_updated_at = datetime.now(timezone.utc)

    # If switching methods, might want to refresh status
    if old_payment_method != new_payment_method:
        # Trigger a status refresh for the new payment method
        try:
            payment_service = current_app.payment_service
            payment_service.refresh_provider_settings(existing_provider_payment_settings)
        except Exception as e:
            current_app.logger.warning(f"Failed to refresh provider status during payment method update: {e}")
            # Don't fail the request if refresh fails

    db.session.commit()

    response = PaymentMethodUpdateResponse(
        message="Payment method updated successfully",
        provider_id=provider_id,
        payment_method=existing_provider_payment_settings.payment_method.value,
        payment_method_updated_at=existing_provider_payment_settings.payment_method_updated_at.isoformat(),
        is_payable=existing_provider_payment_settings.is_payable,
    )

    return response.model_dump_json(), 200, {"Content-Type": "application/json"}


@bp.post("/provider/<string:provider_id>/initialize-payment")
@api_key_required
def initialize_provider_payment(provider_id: str):
    """
    Initialize a provider's Chek account and set up their payment method.
    Can create either a virtual card or send ACH invite.
    Protected by API key for admin use.
    """
    try:
        request_data = PaymentMethodInitializeRequest.model_validate(request.get_json() or {"payment_method": "card"})
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    payment_method = request_data.payment_method

    try:
        payment_service = current_app.payment_service
        result = payment_service.initialize_provider_payment_method(provider_id, payment_method)

        # Convert the result to PaymentInitializationResponse
        response = PaymentInitializationResponse(**result)
        return response.model_dump_json(), 200, {"Content-Type": "application/json"}
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"Failed to initialize payment for provider {provider_id}: {e}")
        return jsonify({"error": f"Failed to initialize payment: {str(e)}"}), 500
    except UnwrapError:
        abort(502, description="Database query failed")


@bp.post("/provider/initialize-my-payment")
@auth_required(ClerkUserType.PROVIDER)
def initialize_my_payment():
    """
    Initialize the authenticated provider's payment method.
    Provider can set up their own card or ACH.
    """
    user = get_provider_user()
    provider_id = user.user_data.provider_id

    try:
        request_data = PaymentMethodInitializeRequest.model_validate(request.get_json() or {"payment_method": "card"})
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    payment_method = request_data.payment_method

    try:
        payment_service = current_app.payment_service
        result = payment_service.initialize_provider_payment_method(provider_id, payment_method)

        # Convert the result to PaymentInitializationResponse for consistency
        response = PaymentInitializationResponse(**result)
        return response.model_dump_json(), 200, {"Content-Type": "application/json"}
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"Failed to initialize payment for provider {provider_id}: {e}")
        return jsonify({"error": f"Failed to initialize payment: {str(e)}"}), 500


@bp.route("/provider/<string:provider_id>/allocated_care_days", methods=["GET"])
@auth_required(ClerkUserType.PROVIDER)
def get_allocated_care_days(provider_id):
    child_id = request.args.get("childId")
    start_date_str = request.args.get("startDate")
    end_date_str = request.args.get("endDate")

    query = AllocatedCareDay.query.filter_by(provider_supabase_id=provider_id)

    if child_id:
        query = query.join(MonthAllocation).filter(MonthAllocation.child_supabase_id == child_id)

    if start_date_str:
        try:
            start_date = date.fromisoformat(start_date_str)
            query = query.filter(AllocatedCareDay.date >= start_date)
        except ValueError:
            return jsonify({"error": "Invalid startDate format. Use YYYY-MM-DD."}), 400

    if end_date_str:
        try:
            end_date = date.fromisoformat(end_date_str)
            query = query.filter(AllocatedCareDay.date <= end_date)
        except ValueError:
            return jsonify({"error": "Invalid endDate format. Use YYYY-MM-DD."}), 400

    care_days = query.all()

    # Group by child
    care_days_by_child = defaultdict(list)
    for day in care_days:
        care_days_by_child[day.care_month_allocation.child_supabase_id].append(day.to_dict())

    return jsonify(care_days_by_child)


@dataclass
class InviteProviderMessage:
    subject: str
    email: str
    sms: str


def get_invite_family_message(lang: str, provider_name: str, link: str):
    language = Language.SPANISH if lang == "es" else Language.ENGLISH
    email_html = InvitationTemplate.get_family_invitation_content(provider_name, link, language)

    if lang == "es":
        return InviteProviderMessage(
            subject=f"Invitación de {provider_name} - ¡Reciba ayuda con los costos de cuidado infantil!",
            email=email_html,
            sms=f"{provider_name} te invitó a unirte al Programa Piloto Childcare Affordability Pilot (CAP). ¡Accede hasta $1,400 mensuales para pagar el cuidado infantil si es aprobado! Haz clic aquí para obtener más información y aplique. {link} ¿Tienes preguntas? Escríbenos a support@capcolorado.org.",
        )

    return InviteProviderMessage(
        subject=f"Invitation from {provider_name} - Receive help with childcare costs!",
        email=email_html,
        sms=f"{provider_name} invited you to join the Childcare Affordability Pilot (CAP) - access up to $1,400 monthly to pay for childcare if approved!  Click here to learn more & apply! {link} Questions? support@capcolorado.org.",
    )


@bp.post("/provider/invite-family")
@auth_required(ClerkUserType.PROVIDER)
def invite_family():
    data = request.json

    if "family_email" not in data:
        abort(400, description="Missing required field: provider_email")
    if "family_cell" not in data:
        abort(400, description="Missing required field: provider_cell")

    if "lang" not in data:
        data["lang"] = "en"

    user = get_provider_user()
    provider_id = user.user_data.provider_id

    provider_result = Provider.select_by_id(
        cols(Provider.ID, Provider.FIRST_NAME, Provider.LAST_NAME), int(provider_id)
    ).execute()

    provider = unwrap_or_abort(provider_result)
    if not provider:
        abort(404, description=f"Provider with ID {provider_id} not found.")

    id = str(uuid4())
    invitation = FamilyInvitation.new(id, data["family_email"], provider_id)
    db.session.add(invitation)

    try:
        domain = current_app.config.get("FRONTEND_DOMAIN")
        link = f"{domain}/invite/family/{id}"

        provider_name = format_name(provider)

        message = get_invite_family_message(
            data["lang"],
            provider_name,
            link,
        )

        from_email = get_from_email_external()
        email_sent = send_email(
            from_email,
            data["family_email"],
            message.subject,
            message.email,
            email_type="provider_family_invitation",
            context_data={
                "provider_name": provider_name,
                "provider_id": str(Provider.ID(provider)),
                "family_email": data["family_email"],
                "invitation_id": str(invitation.public_id),
            },
            is_internal=False,
        )
        if email_sent:
            invitation.record_email_sent()

        if data["family_cell"] is not None:
            sms_sent = send_sms(data["family_cell"], message.sms, data["lang"])
            if sms_sent:
                invitation.record_sms_sent()
    finally:
        db.session.commit()

    send_family_invited_email(provider_name, Provider.ID(provider), data["family_email"], invitation.public_id)

    return jsonify({"message": "Success"}, 201)


@dataclass
class InviteData:
    provider_data: dict
    child_count: int
    remaining_slots: int


def get_invite_data(provider_id: str):
    provider_result = Provider.select_by_id(
        cols(Provider.ID, Provider.FIRST_NAME, Provider.LAST_NAME, Provider.NAME, Child.join(Child.ID)),
        int(provider_id),
    ).execute()
    provider = unwrap_or_abort(provider_result)

    if provider is None:
        abort(500, description=f"Provider with ID {provider_id} not found.")

    children_data = Child.unwrap(provider)
    child_count = len(children_data)
    remaining_slots = MAX_CHILDREN_PER_PROVIDER - child_count

    return InviteData(provider_data=provider, child_count=child_count, remaining_slots=remaining_slots)


@bp.get("/provider/family-invite/<invite_id>")
@auth_optional
def family_invite(invite_id: str):
    invitation_query = FamilyInvitation.invitation_by_id(invite_id)
    invitation = invitation_query.first()

    if invitation is None:
        abort(404, description=f"Family invitation with ID {invite_id} not found.")

    invitation.record_opened()
    db.session.add(invitation)
    db.session.commit()

    user = get_current_user()

    invite_data = get_invite_data(invitation.provider_supabase_id)

    provider = {
        "id": Provider.ID(invite_data.provider_data),
        "first_name": Provider.FIRST_NAME(invite_data.provider_data),
        "last_name": Provider.LAST_NAME(invite_data.provider_data),
    }

    is_already_provider = False

    if user is None or user.user_data.family_id is None:
        children = None
    else:
        family_children_result = Child.select_by_family_id(
            cols(Child.ID, Child.FIRST_NAME, Child.LAST_NAME, Provider.join(Provider.ID)), int(user.user_data.family_id)
        ).execute()

        child_data = unwrap_or_abort(family_children_result)

        children = []
        for child in child_data:
            child_id = Child.ID(child)

            # Check if this child already has the inviting provider
            child_providers = Provider.unwrap(child)
            child_has_provider = any(Provider.ID(p) == invitation.provider_supabase_id for p in child_providers)

            if child_has_provider:
                is_already_provider = True
                continue

            children.append(
                {
                    "id": child_id,
                    "first_name": Child.FIRST_NAME(child),
                    "last_name": Child.LAST_NAME(child),
                }
            )

    return jsonify(
        {
            "accepted": invitation.accepted,
            "provider": provider,
            "children": children,
            "is_already_provider": is_already_provider,
            "remaining_slots": invite_data.remaining_slots,
        }
    )


@bp.post("/provider/family-invite/<invite_id>/accept")
@auth_required(ClerkUserType.FAMILY)
def accept_family_invite(invite_id: str):
    data = request.json

    if "child_ids" not in data:
        abort(400, description="Missing required field: child_ids")
    if type(data["child_ids"]) != list:
        abort(400, description="child_ids must be a list of child IDs")
    if len(data["child_ids"]) == 0:
        abort(400, description="child_ids must not be empty")

    user = get_family_user()

    invitation_query = FamilyInvitation.invitation_by_id(invite_id)
    invitation = invitation_query.first()

    if invitation is None:
        abort(404, description=f"Family invitation with ID {invite_id} not found.")

    if invitation.accepted:
        abort(400, description="Invitation already accepted.")

    invite_data = get_invite_data(invitation.provider_supabase_id)

    if invite_data.remaining_slots - len(data["child_ids"]) < 0:
        abort(400, description="Provider already has maximum number of children.")

    child_ids = [int(child_id) for child_id in data["child_ids"]]

    family_result = Family.select_by_id(
        cols(
            Family.ID,
            Guardian.join(Guardian.FIRST_NAME, Guardian.LAST_NAME, Guardian.TYPE),
            Child.join(Child.ID, Child.FIRST_NAME, Child.LAST_NAME, Child.FAMILY_ID),
        ),
        int(user.user_data.family_id),
    ).execute()

    family_data = unwrap_or_abort(family_result)
    if not family_data:
        abort(404, description=f"Family with ID {user.user_data.family_id} not found.")

    all_children_data = Child.unwrap(family_data)

    # Filter to only the requested children and verify they exist
    children = []
    requested_child_ids = set(child_ids)
    found_child_ids = set()

    for child in all_children_data:
        child_id = int(Child.ID(child))
        if child_id in requested_child_ids:
            children.append(child)
            found_child_ids.add(child_id)

    # Verify all requested children were found
    if len(found_child_ids) != len(child_ids):
        missing_ids = requested_child_ids - found_child_ids
        abort(404, description=f"Children with IDs {list(missing_ids)} not found.")

    primary_guardian = Guardian.get_primary_guardian(Guardian.unwrap(family_data))

    accept_request = send_family_invite_accept_email(
        provider_name=Provider.NAME(invite_data.provider_data),
        provider_id=Provider.ID(invite_data.provider_data),
        parent_name=format_name(primary_guardian),
        parent_id=Family.ID(family_data),
        children=children,
    )

    if not accept_request:
        current_app.logger.error(
            f"Failed to send family invite accept email for family ID {user.user_data.family_id} and provider ID {Provider.ID(invite_data.provider_data)}.",
        )

    invitation.record_accepted()
    db.session.add(invitation)
    db.session.commit()

    return jsonify({"message": "Success"}, 200)
