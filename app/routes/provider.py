from dataclasses import dataclass
from clerk_backend_api import Clerk, CreateInvitationRequestBody
from flask import Blueprint, abort, jsonify, request, current_app
from app.auth.helpers import get_current_user
from app.extensions import db
from app.models import Provider, AllocatedCareDay, MonthAllocation
from app.auth.decorators import ClerkUserType, auth_optional, auth_required, api_key_required
from app.models.family_invitation import FamilyInvitation
from app.sheets.helpers import KeyMap, format_name
from app.sheets.mappings import (
    ChildColumnNames,
    FamilyColumnNames,
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
    get_provider_children,
    get_provider_transactions,
    get_providers,
    get_transactions,
)
from datetime import date
from collections import defaultdict
from uuid import uuid4

from app.utils.email_service import get_from_email_internal, send_email, send_family_invite_accept_email
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

    if Provider.query.filter_by(google_sheet_id=data["google_sheet_id"]).first():
        abort(409, description=f"A provider with that Google Sheet ID already exists.")

    # Create new provider
    provider = Provider.new(google_sheet_id=data["google_sheet_id"])
    db.session.add(provider)
    db.session.commit()

    # send clerk invite
    clerk: Clerk = current_app.clerk_client
    fe_domain = current_app.config.get("FRONTEND_DOMAIN")
    meta_data = {
        "types": [ClerkUserType.PROVIDER],  # NOTE: list in case we need to have people who fit into multiple categories
        "provider_id": provider.id,
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
    user = get_current_user()

    if user is None or user.user_data.provider_id is None:
        abort(401)

    provider_rows = get_providers()
    child_rows = get_children()
    provider_child_mapping_rows = get_provider_child_mappings()
    transaction_rows = get_transactions()

    provider_id = user.user_data.provider_id  # TODO: Get Google Sheet ID from DB

    provider_data = get_provider(provider_id, provider_rows)
    children_data = get_provider_children(provider_id, provider_child_mapping_rows, child_rows)
    transaction_data = get_provider_transactions(provider_id, provider_child_mapping_rows, transaction_rows)

    provider_info = {
        "id": provider_data.get(ProviderColumnNames.ID),
        "first_name": provider_data.get(ProviderColumnNames.FIRST_NAME),
        "last_name": provider_data.get(ProviderColumnNames.LAST_NAME),
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

    return jsonify(
        {
            "provider_info": provider_info,
            "children": children,
            "transactions": transactions,
            "curriculum": None,
            "is_also_family": ClerkUserType.FAMILY.value in user.user_data.types,
        }
    )


@bp.route("/provider/<int:provider_id>/allocated_care_days", methods=["GET"])
@auth_required(ClerkUserType.PROVIDER)
def get_allocated_care_days(provider_id):
    child_id = request.args.get("childId", type=int)
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
            email=f'<html><body>{provider_name} lo ha invitado a unirse al Programa Piloto Childcare Affordability Pilot (CAP) como familia participante: ¡puede acceder hasta $1,400 por mes para pagar el cuidado infantil!<br><br>Si presenta su solicitud y su solicitud es aprobada, CAP le proporcionará fondos que puede usar para pagar a {provider_name} o otros cuidadores que participen en el programa piloto.<br><br>¡Haga clic <a href="{link}" style="color: #0066cc; text-decoration: underline;">aquí</a> para aceptar la invitación y aplique!<br><br>¿Tienes preguntas? Escríbenos a support@capcolorado.org.</body></html>',
            sms=f"{provider_name} te invitó a unirte al Programa Piloto Childcare Affordability Pilot (CAP). ¡Acceso hasta $1,400 mensuales para pagar el cuidado infantil si es aprobado! Haz clic aquí para obtener más información y aplique. {link} ¿Tienes preguntas? Escríbenos a support@capcolorado.org.",
        )

    return InviteProviderMessage(
        subject=f"Invitation from {provider_name} - Receive help with childcare costs!",
        email=f'<html><body>{provider_name} has invited you to join the Childcare Affordability Pilot (CAP) as a participating family — you can access up to $1,400 per month to pay for childcare!<br><br>If you apply and are approved, CAP provides funds you can use to pay {provider_name} or other caregivers that participate in the pilot.<br><br>Click <a href="{link}" style="color: #0066cc; text-decoration: underline;">here</a> to accept the invitation and apply! Questions? Email us at support@capcolorado.org.</body></html>',
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

    user = get_current_user()
    if user is None or user.user_data.provider_id is None:
        abort(401)

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


def get_invite_data(provider_id: int):
    provider_rows = get_providers()

    provider = get_provider(provider_id, provider_rows)

    if provider is None:
        abort(500, description=f"Provider with ID {provider_id} not found.")

    return provider


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

    provider_data = get_invite_data(invitation.provider_google_sheet_id)

    provider = {
        "id": provider_data.get(ProviderColumnNames.ID),
        "first_name": provider_data.get(ProviderColumnNames.FIRST_NAME),
        "last_name": provider_data.get(ProviderColumnNames.LAST_NAME),
    }

    if user is None or user.user_data.family_id is None:
        children = None
    else:
        child_rows = get_children()
        child_data = get_family_children(user.user_data.family_id, child_rows)

        children = []
        for child in child_data:
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

    user = get_current_user()

    if user is None or user.user_data.family_id is None:
        abort(401)

    invitation_query = FamilyInvitation.invitation_by_id(invite_id)

    invitation = invitation_query.first()

    if invitation is None:
        abort(404, description=f"Family invitation with ID {invite_id} not found.")

    if invitation.accepted:
        abort(400, description="Invitation already accepted.")

    provider = get_invite_data(invitation.provider_google_sheet_id)

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
            abort(404, description="Child with ID {child_id} not found.")

        children.append(child)

    accept_request = send_family_invite_accept_email(
        provider_name=provider.get(ProviderColumnNames.NAME),
        provider_id=provider.get(ProviderColumnNames.ID),
        parent_name=format_name(family_data),
        parent_id=family_data.get(FamilyColumnNames.ID),
        children=children,
    )

    if not accept_request:
        current_app.logger.error(
            f"Failed to send family invite accept email for family ID {user.user_data.family_id} and provider ID {provider.get(ProviderColumnNames.ID)}.",
        )

    invitation.record_accepted()
    db.session.add(invitation)
    db.session.commit()

    return jsonify({"message": "Success"}, 200)
