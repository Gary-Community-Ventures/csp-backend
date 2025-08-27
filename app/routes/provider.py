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
from app.config import PROVIDER_STATUS_STALE_SECONDS
from app.constants import MAX_CHILDREN_PER_PROVIDER
from app.enums.payment_method import PaymentMethod
from app.extensions import db
from app.models import AllocatedCareDay, MonthAllocation
from app.models.attendance import Attendance
from app.models.family_invitation import FamilyInvitation
from app.models.provider_payment_settings import ProviderPaymentSettings
from app.schemas.payment import PaymentInitializationResponse
from app.schemas.provider_payment import (
    PaymentMethodInitializeRequest,
    PaymentMethodUpdateRequest,
    PaymentMethodUpdateResponse,
    PaymentSettingsResponse,
)
from app.sheets.helpers import KeyMap, format_name, get_row
from app.sheets.mappings import (
    ChildColumnNames,
    FamilyColumnNames,
    ProviderChildMappingColumnNames,
    ProviderColumnNames,
    TransactionColumnNames,
    get_child,
    get_children,
    get_families,
    get_family,
    get_family_children,
    get_provider,
    get_provider_child_mapping_child,
    get_provider_child_mappings,
    get_provider_child_mappings_by_provider_id,
    get_provider_children,
    get_provider_transactions,
    get_providers,
    get_transactions,
)
from app.utils.email_service import (
    get_from_email_internal,
    html_link,
    send_email,
    send_family_invite_accept_email,
)
from app.utils.sms_service import send_sms

bp = Blueprint("provider", __name__)


@bp.post("/provider")
@api_key_required
def new_provider():
    data = request.json

    # Validate required fields
    if "google_sheet_id" not in data:
        abort(400, description="Missing required fields: google_sheet_id")

    if "email" not in data:
        abort(400, description="Missing required field: email")

    # Create Chek user and ProviderPaymentSettings
    try:
        payment_service = current_app.payment_service
        provider_settings = payment_service.onboard_provider(provider_external_id=data["google_sheet_id"])
        current_app.logger.info(
            f"Created ProviderPaymentSettings for provider {data['google_sheet_id']} with Chek user {provider_settings.chek_user_id}"
        )
    except Exception as e:
        current_app.logger.error(f"Failed to create Chek user for provider {data['google_sheet_id']}: {e}")
        # Don't fail the entire request if Chek onboarding fails
        # Provider can be onboarded to Chek later

    # send clerk invite
    clerk: Clerk = current_app.clerk_client
    fe_domain = current_app.config.get("FRONTEND_DOMAIN")
    meta_data = {
        "types": [ClerkUserType.PROVIDER],  # NOTE: list in case we need to have people who fit into multiple categories
        "provider_id": data["google_sheet_id"],
    }

    clerk.invitations.create(
        request=CreateInvitationRequestBody(
            email_address=data["email"],
            redirect_url=f"{fe_domain}/auth/sign-up",
            public_metadata=meta_data,
        )
    )

    return jsonify(data)


@bp.get("/provider")
@auth_required(ClerkUserType.PROVIDER)
def get_provider_data():
    user = get_provider_user()

    provider_rows = get_providers()
    child_rows = get_children()
    provider_child_mapping_rows = get_provider_child_mappings()
    transaction_rows = get_transactions()

    provider_id = user.user_data.provider_id

    provider_data = get_provider(provider_id, provider_rows)
    children_data = get_provider_children(provider_id, provider_child_mapping_rows, child_rows)
    transaction_data = get_provider_transactions(provider_id, provider_child_mapping_rows, transaction_rows)

    provider_payment_settings = ProviderPaymentSettings.query.filter_by(provider_external_id=provider_id).first()

    provider_info = {
        "id": provider_data.get(ProviderColumnNames.ID),
        "first_name": provider_data.get(ProviderColumnNames.FIRST_NAME),
        "last_name": provider_data.get(ProviderColumnNames.LAST_NAME),
        "is_payable": provider_payment_settings.is_payable if provider_payment_settings else False,
    }

    children = [
        {
            "id": c.get(ChildColumnNames.ID),
            "first_name": c.get(ChildColumnNames.FIRST_NAME),
            "last_name": c.get(ChildColumnNames.LAST_NAME),
        }
        for c in children_data
    ]

    transactions = []
    for t in transaction_data:
        transaction_child = get_provider_child_mapping_child(
            t.get(TransactionColumnNames.PROVIDER_CHILD_ID),
            provider_child_mapping_rows,
            child_rows,
        )
        transactions.append(
            {
                "id": t.get(TransactionColumnNames.ID),
                "name": f"{transaction_child.get(ChildColumnNames.FIRST_NAME)} {transaction_child.get(ChildColumnNames.LAST_NAME)}",
                "amount": t.get(TransactionColumnNames.AMOUNT),
                "date": t.get(TransactionColumnNames.DATETIME).isoformat(),
            }
        )

    notifications = []
    provider_status = provider_data.get(ProviderColumnNames.STATUS).lower()
    if provider_status == "pending":
        notifications.append({"type": "application_pending"})
    elif provider_status == "denied":
        notifications.append({"type": "application_denied"})

    needs_attendance = Attendance.filter_by_provider_id(provider_id).count() > 0
    if needs_attendance:
        notifications.append({"type": "attendance"})

    return jsonify(
        {
            "provider_info": provider_info,
            "children": children,
            "transactions": transactions,
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
    provider_payment_settings = ProviderPaymentSettings.query.filter_by(provider_external_id=provider_id).first()

    if not provider_payment_settings:
        # Onboard provider to Chek when first accessing payment settings
        try:
            payment_service = current_app.payment_service
            provider_payment_settings = payment_service.onboard_provider(provider_external_id=provider_id)
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
        if time_since_sync.total_seconds() > PROVIDER_STATUS_STALE_SECONDS:
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
        provider_external_id=provider_id
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
            payment_service.refresh_provider_status(existing_provider_payment_settings)
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
        result = payment_service.initialize_provider_payment(provider_id, payment_method)

        # Convert the result to PaymentInitializationResponse
        response = PaymentInitializationResponse(**result)
        return response.model_dump_json(), 200, {"Content-Type": "application/json"}
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"Failed to initialize payment for provider {provider_id}: {e}")
        return jsonify({"error": f"Failed to initialize payment: {str(e)}"}), 500


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
        result = payment_service.initialize_provider_payment(provider_id, payment_method)

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

    query = AllocatedCareDay.query.filter_by(provider_google_sheets_id=provider_id)

    if child_id:
        query = query.join(MonthAllocation).filter(MonthAllocation.google_sheets_child_id == child_id)

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
        care_days_by_child[day.care_month_allocation.google_sheets_child_id].append(day.to_dict())

    return jsonify(care_days_by_child)


@dataclass
class InviteProviderMessage:
    subject: str
    email: str
    sms: str


def get_invite_family_message(lang: str, provider_name: str, link: str):
    if lang == "es":
        return InviteProviderMessage(
            subject=f"Invitación de {provider_name} - ¡Reciba ayuda con los costos de cuidado infantil!",
            email=f'<html><body>{provider_name} lo ha invitado a unirse al Programa Piloto Childcare Affordability Pilot (CAP) como familia participante: ¡puede acceder hasta $1,400 por mes para pagar el cuidado infantil!<br><br>Si presenta su solicitud y su solicitud es aprobada, CAP le proporcionará fondos que puede usar para pagar a {provider_name} o otros cuidadores que participen en el programa piloto.<br><br>¡Haga clic {html_link(link, "aquí")} para aceptar la invitación y aplique!<br><br>¿Tienes preguntas? Escríbenos a support@capcolorado.org.</body></html>',
            sms=f"{provider_name} te invitó a unirte al Programa Piloto Childcare Affordability Pilot (CAP). ¡Accede hasta $1,400 mensuales para pagar el cuidado infantil si es aprobado! Haz clic aquí para obtener más información y aplique. {link} ¿Tienes preguntas? Escríbenos a support@capcolorado.org.",
        )

    return InviteProviderMessage(
        subject=f"Invitation from {provider_name} - Receive help with childcare costs!",
        email=f'<html><body>{provider_name} has invited you to join the Childcare Affordability Pilot (CAP) as a participating family — you can access up to $1,400 per month to pay for childcare!<br><br>If you apply and are approved, CAP provides funds you can use to pay {provider_name} or other caregivers that participate in the pilot.<br><br>Click {html_link(link, "here")} to accept the invitation and apply! Questions? Email us at support@capcolorado.org.</body></html>',
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

    proivder_rows = get_providers()

    provider = get_provider(provider_id, proivder_rows)

    if provider is None:
        abort(404, description=f"Provider with ID {provider_id} not found.")

    id = str(uuid4())
    invitation = FamilyInvitation.new(id, data["family_email"], provider_id)
    db.session.add(invitation)

    try:
        domain = current_app.config.get("FRONTEND_DOMAIN")
        link = f"{domain}/invite/family/{id}"

        message = get_invite_family_message(
            data["lang"],
            format_name(provider),
            link,
        )

        from_email = get_from_email_internal()
        email_sent = send_email(from_email, data["family_email"], message.subject, message.email)
        if email_sent:
            invitation.record_email_sent()

        if data["family_cell"] is not None:
            sms_sent = send_sms(data["family_cell"], message.sms, data["lang"])
            if sms_sent:
                invitation.record_sms_sent()
    finally:
        db.session.commit()

    return jsonify({"message": "Success"}, 201)


@dataclass
class InviteData:
    provider_data: KeyMap
    child_provider_mappings: list[KeyMap]
    remaining_slots: int


def get_invite_data(provider_id: int):
    provider_rows = get_providers()
    provider_child_mapping_rows = get_provider_child_mappings()

    provider = get_provider(provider_id, provider_rows)

    if provider is None:
        abort(500, description=f"Provider with ID {provider_id} not found.")

    current_children_mappings = get_provider_child_mappings_by_provider_id(provider_id, provider_child_mapping_rows)
    remaining_slots = MAX_CHILDREN_PER_PROVIDER - len(current_children_mappings)

    return InviteData(
        provider_data=provider, child_provider_mappings=current_children_mappings, remaining_slots=remaining_slots
    )


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

    invite_data = get_invite_data(invitation.provider_google_sheet_id)

    provider = {
        "id": invite_data.provider_data.get(ProviderColumnNames.ID),
        "first_name": invite_data.provider_data.get(ProviderColumnNames.FIRST_NAME),
        "last_name": invite_data.provider_data.get(ProviderColumnNames.LAST_NAME),
    }

    is_already_provider = False

    if user is None or user.user_data.family_id is None:
        children = None
    else:
        child_rows = get_children()
        child_data = get_family_children(user.user_data.family_id, child_rows)

        children = []
        for child in child_data:
            if (
                get_row(
                    invite_data.child_provider_mappings,
                    child.get(ChildColumnNames.ID),
                    id_key=ProviderChildMappingColumnNames.CHILD_ID,
                )
                is not None
            ):
                is_already_provider = True
                continue

            children.append(
                {
                    "id": child.get(ChildColumnNames.ID),
                    "first_name": child.get(ChildColumnNames.FIRST_NAME),
                    "last_name": child.get(ChildColumnNames.LAST_NAME),
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

    invite_data = get_invite_data(invitation.provider_google_sheet_id)

    if invite_data.remaining_slots - len(data["child_ids"]) < 0:
        abort(400, description="Provider already has maximum number of children.")

    family_rows = get_families()
    child_rows = get_children()

    family_data = get_family(user.user_data.family_id, family_rows)

    if family_data is None:
        abort(404, description=f"Family with ID {user.user_data.family_id} not found.")

    children: list[KeyMap] = []
    for child_id in data["child_ids"]:
        child = get_child(child_id, child_rows)

        if child is None:
            abort(404, description=f"Child with ID {child_id} not found.")
        if family_data.get(FamilyColumnNames.ID) != child.get(ChildColumnNames.FAMILY_ID):
            abort(404, description=f"Child with ID {child_id} not found.")

        children.append(child)

    accept_request = send_family_invite_accept_email(
        provider_name=invite_data.provider_data.get(ProviderColumnNames.NAME),
        provider_id=invite_data.provider_data.get(ProviderColumnNames.ID),
        parent_name=format_name(family_data),
        parent_id=family_data.get(FamilyColumnNames.ID),
        children=children,
    )

    if not accept_request:
        current_app.logger.error(
            f"Failed to send family invite accept email for family ID {user.user_data.family_id} and provider ID {invite_data.provider_data.get(ProviderColumnNames.ID)}.",
        )

    invitation.record_accepted()
    db.session.add(invitation)
    db.session.commit()

    return jsonify({"message": "Success"}, 200)
