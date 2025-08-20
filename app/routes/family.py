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
from app.constants import MAX_CHILDREN_PER_PROVIDER
from app.data.providers.mappings import ProviderListColumnNames
from app.extensions import db
from app.models.attendance import Attendance
from app.models.provider_invitation import ProviderInvitation
from app.sheets.helpers import KeyMap, format_name, get_row
from app.sheets.integration import get_csv_data
from app.sheets.mappings import (
    ChildColumnNames,
    FamilyColumnNames,
    ProviderChildMappingColumnNames,
    ProviderColumnNames,
    TransactionColumnNames,
    get_child,
    get_child_providers,
    get_child_transactions,
    get_children,
    get_families,
    get_family,
    get_family_children,
    get_provider_child_mapping_provider,
    get_provider_child_mappings,
    get_provider_child_mappings_by_provider_id,
    get_providers,
    get_transactions,
)
from app.utils.email_service import (
    get_from_email_internal,
    html_link,
    send_add_licensed_provider_email,
    send_email,
    send_provider_invite_accept_email,
)
from app.utils.sms_service import send_sms

bp = Blueprint("family", __name__)


@bp.post("/family")
@api_key_required
def new_family():
    data = request.json

    # Validate required fields
    if "google_sheet_id" not in data:
        abort(400, description="Missing required fields: google_sheet_id")

    if "email" not in data:
        abort(400, description="Missing required field: email")

    # send clerk invite
    clerk: Clerk = current_app.clerk_client
    fe_domain = current_app.config.get("FRONTEND_DOMAIN")
    meta_data = {
        "types": [ClerkUserType.FAMILY],  # NOTE: list in case we need to have people who fit into multiple categories
        "family_id": data["google_sheet_id"],
    }

    clerk.invitations.create(
        request=CreateInvitationRequestBody(
            email_address=data["email"],
            redirect_url=f"{fe_domain}/auth/sign-up",
            public_metadata=meta_data,
        )
    )

    return jsonify(data)


@bp.get("/family/default_child_id")
@auth_required(ClerkUserType.FAMILY)
def default_child_id():
    user = get_family_user()

    child_rows = get_children()

    family_id = user.user_data.family_id
    family_children = get_family_children(family_id, child_rows)

    if len(family_children) == 0:
        abort(404, description="No children found for this family.")

    active_child_id = family_children[0].get(ChildColumnNames.ID)

    return jsonify({"child_id": active_child_id})


@bp.get("/family/")
@bp.get("/family/<child_id>")
@auth_required(ClerkUserType.FAMILY)
def family_data(child_id: Optional[str] = None):
    user = get_family_user()

    child_rows = get_children()
    provider_child_mapping_rows = get_provider_child_mappings()
    provider_rows = get_providers()
    transaction_rows = get_transactions()

    family_id = user.user_data.family_id
    family_children = get_family_children(family_id, child_rows)

    if len(family_children) == 0:
        abort(404, description="No children found for this family.")

    if child_id is not None:
        selected_child = get_child(child_id, family_children)

        if selected_child is None:
            abort(404, description=f"Child with ID {child_id} not found.")

        active_child_id = child_id
    else:
        active_child_id = family_children[0].get(ChildColumnNames.ID)

    child_data = get_child(active_child_id, child_rows)
    provider_data = get_child_providers(active_child_id, provider_child_mapping_rows, provider_rows)
    transaction_data = get_child_transactions(active_child_id, provider_child_mapping_rows, transaction_rows)

    selected_child_info = {
        "id": child_data.get(ChildColumnNames.ID),
        "first_name": child_data.get(ChildColumnNames.FIRST_NAME),
        "last_name": child_data.get(ChildColumnNames.LAST_NAME),
        "balance": child_data.get(ChildColumnNames.BALANCE),
        "monthly_allocation": child_data.get(ChildColumnNames.MONTHLY_ALLOCATION),
        "prorated_first_month_allocation": child_data.get(ChildColumnNames.PRORATED_FIRST_MONTH_ALLOCATION),
    }

    providers = [
        {
            "id": c.get(ProviderColumnNames.ID),
            "name": c.get(ProviderColumnNames.NAME),
            "status": c.get(ProviderColumnNames.STATUS).lower(),
        }
        for c in provider_data
    ]

    transactions = [
        {
            "id": t.get(TransactionColumnNames.ID),
            "name": get_provider_child_mapping_provider(
                t.get(TransactionColumnNames.PROVIDER_CHILD_ID),
                provider_child_mapping_rows,
                provider_rows,
            ).get(ProviderColumnNames.NAME),
            "amount": t.get(TransactionColumnNames.AMOUNT),
            "date": t.get(TransactionColumnNames.DATETIME).isoformat(),
        }
        for t in transaction_data
    ]

    children = [
        {
            "id": c.get(ChildColumnNames.ID),
            "first_name": c.get(ChildColumnNames.FIRST_NAME),
            "last_name": c.get(ChildColumnNames.LAST_NAME),
        }
        for c in family_children
    ]

    notifications = []
    child_status = child_data.get(ChildColumnNames.STATUS).lower()
    if child_status == "pending":
        notifications.append({"type": "application_pending"})
    elif child_status == "denied":
        notifications.append({"type": "application_denied"})

    child_ids = [c.get(ChildColumnNames.ID) for c in family_children]
    needs_attendance = Attendance.filter_by_child_ids(child_ids).count() > 0
    if needs_attendance:
        notifications.append({"type": "attendance"})

    return jsonify(
        {
            "selected_child_info": selected_child_info,
            "providers": providers,
            "transactions": transactions,
            "children": children,
            "notifications": notifications,
            "is_also_provider": ClerkUserType.PROVIDER.value in user.user_data.types,
        }
    )


@bp.get("/family/licensed-providers")
@auth_required(ClerkUserType.FAMILY)
def licensed_providers():
    data = get_csv_data("app/data/providers/list.csv")

    providers = []
    for row in data:
        providers.append(
            {
                "license_number": row.get(ProviderListColumnNames.LICENSE_NUMBER),
                "name": row.get(ProviderListColumnNames.PROVIDER_NAME),
                "address": {
                    "street_address": row.get(ProviderListColumnNames.STREET_ADDRESS),
                    "city": row.get(ProviderListColumnNames.CITY),
                    "state": row.get(ProviderListColumnNames.STATE),
                    "zip": row.get(ProviderListColumnNames.ZIP),
                    "county": row.get(ProviderListColumnNames.COUNTY),
                },
                "rating": row.get(ProviderListColumnNames.QUALITY_RATING),
            }
        )

    return jsonify({"providers": providers})


@bp.post("/family/licensed-providers")
@auth_required(ClerkUserType.FAMILY)
def add_licensed_provider():
    data = request.json

    # Validate required fields
    if "license_number" not in data:
        abort(400, description="Missing required field: license_number")
    if "child_ids" not in data:
        abort(400, description="Missing required field: child_ids")
    if type(data["child_ids"]) != list:
        abort(400, description="child_ids must be a list of child IDs")

    user = get_family_user()

    family_id = user.user_data.family_id

    child_rows = get_children()
    family_rows = get_families()

    licensed_provideer_rows = get_csv_data("app/data/providers/list.csv")

    provider = get_row(
        licensed_provideer_rows,
        data["license_number"],
        id_key=ProviderListColumnNames.LICENSE_NUMBER,
    )
    if provider is None:
        abort(
            404,
            description=f"Provider with license number {data['license_number']} not found.",
        )

    family = get_family(family_id, family_rows)
    if family is None:
        abort(404, description=f"Family with ID {family_id} not found.")

    family_children = get_family_children(family_id, child_rows)

    children: list[KeyMap] = []
    for child_id in data["child_ids"]:
        child = get_child(child_id, family_children)

        if child is None:
            abort(404, description=f"Child with ID {child_id} not found.")

        children.append(child)

    send_add_licensed_provider_email(
        license_number=provider.get(ProviderListColumnNames.LICENSE_NUMBER),
        provider_name=provider.get(ProviderListColumnNames.PROVIDER_NAME),
        parent_name=format_name(family),
        parent_id=family.get(FamilyColumnNames.ID),
        children=children,
    )

    return jsonify({"message": "Success"}, 201)


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

    child_rows = get_children()
    family_rows = get_families()

    family = get_family(family_id, family_rows)
    if family is None:
        abort(404, description=f"Family with ID {family_id} not found.")

    family_children = get_family_children(family_id, child_rows)

    children: list[KeyMap] = []
    for child_id in data["child_ids"]:
        child = get_child(child_id, family_children)

        if child is None:
            abort(404, description=f"Child with ID {child_id} not found.")

        children.append(child)

    for child in children:
        try:
            child_id = child.get(ChildColumnNames.ID)
            id = str(uuid4())

            invitation = ProviderInvitation.new(id, data["provider_email"], child_id)
            db.session.add(invitation)

            domain = current_app.config.get("FRONTEND_DOMAIN")
            link = f"{domain}/invite/provider/{id}"

            message = get_invite_provider_message(
                data["lang"],
                format_name(family),
                format_name(child),
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

    return jsonify({"message": "Success"}, 201)


@dataclass
class InviteData:
    child_data: KeyMap
    family_data: KeyMap
    current_child_count: int
    already_caring_for: bool = False
    at_max_child_count: bool = False


def get_invite_data(child_id: list[str], provider_id: Optional[str] = None):
    current_children_mappings: list[KeyMap] = []
    if provider_id is not None:
        provider_child_mapping_rows = get_provider_child_mappings()
        current_children_mappings = get_provider_child_mappings_by_provider_id(provider_id, provider_child_mapping_rows)

    child_rows = get_children()
    family_rows = get_families()

    child_data = get_row(child_rows, child_id)

    if child_data is None:
        abort(404, description=f"Child with ID {child_id} not found.")
    family_data = get_family(child_data.get(ChildColumnNames.FAMILY_ID), family_rows)

    if family_data is None:
        abort(404, description=f"Family with ID {child_data.get(ChildColumnNames.FAMILY_ID)} not found.")

    invite_data = InviteData(
        child_data=child_data, family_data=family_data, current_child_count=len(current_children_mappings)
    )

    # Remove any children that the provider already has
    for current_child_mapping in current_children_mappings:
        if current_child_mapping.get(ProviderChildMappingColumnNames.CHILD_ID) == child_data.get(ChildColumnNames.ID):
            invite_data.already_caring_for = True

    if len(current_children_mappings) >= MAX_CHILDREN_PER_PROVIDER:
        invite_data.at_max_child_count = True

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
        "id": invite_data.child_data.get(ChildColumnNames.ID),
        "first_name": invite_data.child_data.get(ChildColumnNames.FIRST_NAME),
        "last_name": invite_data.child_data.get(ChildColumnNames.LAST_NAME),
    }

    family = {
        "id": invite_data.family_data.get(FamilyColumnNames.ID),
        "first_name": invite_data.family_data.get(FamilyColumnNames.FIRST_NAME),
        "last_name": invite_data.family_data.get(FamilyColumnNames.LAST_NAME),
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

    provider_rows = get_providers()

    provider = get_row(provider_rows, user.user_data.provider_id)

    if invite_data.at_max_child_count:
        abort(400, description=f"Provider cannot have more than {MAX_CHILDREN_PER_PROVIDER} children.")

    if invite_data.already_caring_for:
        abort(400, description=f"Provider already has a child in the family.")

    accept_request = send_provider_invite_accept_email(
        provider_name=provider.get(ProviderColumnNames.NAME),
        provider_id=provider.get(ProviderColumnNames.ID),
        parent_name=format_name(invite_data.family_data),
        parent_id=invite_data.family_data.get(FamilyColumnNames.ID),
        child_name=format_name(invite_data.child_data),
        child_id=invite_data.child_data.get(ChildColumnNames.ID),
    )

    if not accept_request:
        current_app.logger.error(
            f"Failed to send provider invite accept email for provider ID {user.user_data.provider_id} and family ID {invite_data.family_data.get(FamilyColumnNames.ID)}.",
        )

    invitation.record_accepted()
    db.session.add(invitation)
    db.session.commit()

    return jsonify({"message": "Success"}, 200)
