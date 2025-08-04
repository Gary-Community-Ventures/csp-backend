from dataclasses import dataclass
from typing import Optional
from datetime import date
from clerk_backend_api import Clerk, CreateInvitationRequestBody
from flask import Blueprint, abort, jsonify, request, current_app
from app.data.providers.mappings import ProviderListColumnNames
from app.extensions import db
from app.models.family import Family
from app.auth.decorators import ClerkUserType, auth_optional, auth_required, api_key_required
from app.auth.helpers import get_current_user
from app.models.provider_invitation import ProviderInvitation
from app.sheets.helpers import KeyMap, format_name, get_row, get_rows
from app.sheets.integration import get_csv_data
from app.sheets.mappings import (
    FamilyColumnNames,
    ProviderColumnNames,
    ChildColumnNames,
    TransactionColumnNames,
    get_families,
    get_family,
    get_provider_child_mapping_provider,
    get_provider_child_mappings,
    get_providers,
    get_child,
    get_child_providers,
    get_children,
    get_child_transactions,
    get_family_children,
    get_transactions,
)
from app.utils.email_service import (
    get_from_email_internal,
    send_add_licensed_provider_email,
    send_email,
    send_provider_invite_accept_email,
)
from uuid import uuid4
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

    if Family.query.filter_by(google_sheet_id=data["google_sheet_id"]).first():
        abort(409, description=f"A family with that Google Sheet ID already exists.")

    # Create new family
    family = Family.new(google_sheet_id=data["google_sheet_id"])
    db.session.add(family)
    db.session.commit()

    # send clerk invite
    clerk: Clerk = current_app.clerk_client
    fe_domain = current_app.config.get("FRONTEND_DOMAIN")
    meta_data = {
        "types": [ClerkUserType.FAMILY],  # NOTE: list in case we need to have people who fit into multiple categories
        "family_id": family.id,
    }

    clerk.invitations.create(
        request=CreateInvitationRequestBody(
            email_address=data["email"], redirect_url=f"{fe_domain}/auth/sign-up", public_metadata=meta_data
        )
    )

    return jsonify(data)


@bp.get("/family/default_child_id")
@auth_required(ClerkUserType.FAMILY)
def default_child_id():
    user = get_current_user()

    if user is None or user.user_data.family_id is None:
        abort(401)

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
    user = get_current_user()

    if user is None or user.user_data.family_id is None:
        abort(401)

    child_rows = get_children()
    provider_child_mapping_rows = get_provider_child_mappings()
    provider_rows = get_providers()
    transaction_rows = get_transactions()

    family_id = user.user_data.family_id
    family_children = get_family_children(family_id, child_rows)

    if len(family_children) == 0:
        abort(404, description="No children found for this family.")

    if child_id is not None:
        try:
            child_id = int(child_id)
        except ValueError:
            abort(400, description=f"Invalid child ID: {child_id}")

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
                t.get(TransactionColumnNames.PROVIDER_CHILD_ID), provider_child_mapping_rows, provider_rows
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

    return jsonify(
        {
            "selected_child_info": selected_child_info,
            "providers": providers,
            "transactions": transactions,
            "children": children,
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

    user = get_current_user()
    if user is None or user.user_data.family_id is None:
        abort(401)

    family_id = user.user_data.family_id

    child_rows = get_children()
    family_rows = get_families()

    licensed_provideer_rows = get_csv_data("app/data/providers/list.csv")

    provider = get_row(licensed_provideer_rows, data["license_number"], id_key=ProviderListColumnNames.LICENSE_NUMBER)
    if provider is None:
        abort(404, description=f"Provider with license number {data['license_number']} not found.")

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


def get_invite_provider_message(lang: str, family_name: str, child_names: list[str], link: str):
    formatted_child_names = ", ".join([child_name for child_name in child_names])
    if lang == "es":
        return InviteProviderMessage(
            subject=f"¡{family_name} se complace en invitarte al programa CAP!",
            email=f'<html><body>¡{family_name} te invitó a unirte al programa CAP para cuidar a {formatted_child_names}!<br><br>CAP ayuda a las familias a pagar el cuidado infantil y a proveedores como tú a recibir su pago. Únete a este programa piloto de 9 meses y obtén pagos flexibles por el cuidado que ya brindas.<br><br><a href="{link}" style="color: #0066cc; text-decoration: underline;">Toque para aceptar</a><br><br>¿Preguntas? cap@garycommunity.org</body></html>',
            sms=f"¡{family_name} te invitó a unirte al programa CAP para cuidar a {child_names}! CAP ayuda a las familias a pagar el cuidado infantil y a proveedores como tú a recibir su pago. Únete a este programa piloto de 9 meses y obtén pagos flexibles por el cuidado que ya brindas. Toque para aceptar: {link} ¿Preguntas? cap@garycommunity.org",
        )

    return InviteProviderMessage(
        subject=f"{family_name} is excited to invite you to the CAP program!",
        email=f'<html><body>{family_name} has invited you to join the Childcare Affordability Pilot (CAP) as a provider for {formatted_child_names}—and we’d love to have you on board!<br><br>CAP is a 9-month program that helps families pay for childcare and helps providers like you get paid. You’ll receive payments through the CAP app, keep your usual care routines, and support families you already work with—or new ones.<br><br>Click <a href="{link}" style="color: #0066cc; text-decoration: underline;">here</a> to accept the invitation and get started!<br><br>Questions? Email us at cap@garycommunity.org.</body></html>',
        sms=f"{family_name} invited you to join the CAP program to provide care for {formatted_child_names}! CAP helps families pay for childcare—and helps providers like you get paid. Join this 9-month pilot and get flexible payments for care you already provide. Tap to accept: {link} Questions? cap@garycommunity.org",
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

    user = get_current_user()
    if user is None or user.user_data.family_id is None:
        abort(401)

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

    id = str(uuid4())
    child_ids = [child.get(ChildColumnNames.ID) for child in children]

    invitations = ProviderInvitation.new(id, data["provider_email"], child_ids)
    db.session.add_all(invitations)

    try:
        domain = current_app.config.get("FRONTEND_DOMAIN")
        link = f"{domain}/invite/provider/{id}"
        child_names = [format_name(child) for child in children]

        message = get_invite_provider_message(
            data["lang"],
            format_name(family),
            child_names,
            link,
        )

        from_email = get_from_email_internal()
        if data["provider_email"] != "":
            email_sent = send_email(from_email, data["provider_email"], message.subject, message.email)
            if email_sent:
                for invitation in invitations:
                    invitation.record_email_sent()

        if data["provider_cell"] != "":
            sms_sent = send_sms(data["provider_cell"], message.sms, data["lang"])
            if sms_sent:
                for invitation in invitations:
                    invitation.record_sms_sent()
    finally:
        db.session.commit()

    return jsonify({"message": "Success"}, 201)


def get_invite_data(child_ids: list[int]):
    child_rows = get_children()
    family_rows = get_families()

    child_data = get_rows(child_rows, child_ids)

    if len(child_data) == 0:
        abort(500, description="Child not found.")

    for child in child_data:
        if child.get(ChildColumnNames.FAMILY_ID) != child_data[0].get(ChildColumnNames.FAMILY_ID):
            abort(500, description="Child not found.")  # make sure that all the children are in the same family

    family_data = get_family(child_data[0].get(ChildColumnNames.FAMILY_ID), family_rows)
    if family_data is None:
        abort(500, description="Family not found.")

    return child_data, family_data


@bp.get("/family/provider-invite/<invite_id>")
@auth_optional
def provider_invite(invite_id: str):
    invitations = ProviderInvitation.invitations_by_id(invite_id)

    child_ids: list[int] = []
    accepted = False
    for invitation in invitations:
        if invitation.accepted:
            accepted = True
        child_ids.append(int(invitation.child_google_sheet_id))
        invitation.record_opened()

    db.session.add_all(invitations)
    db.session.commit()

    child_data, family_data = get_invite_data(child_ids)

    children = []
    for child in child_data:
        children.append(
            {
                "id": child.get(ChildColumnNames.ID),
                "first_name": child.get(ChildColumnNames.FIRST_NAME),
                "last_name": child.get(ChildColumnNames.LAST_NAME),
            }
        )

    family = {
        "id": family_data.get(FamilyColumnNames.ID),
        "first_name": family_data.get(FamilyColumnNames.FIRST_NAME),
        "last_name": family_data.get(FamilyColumnNames.LAST_NAME),
    }

    return jsonify(
        {
            "accepted": accepted,
            "children": children,
            "family": family,
        }
    )


@bp.post("/family/provider-invite/<invite_id>/accept")
@auth_required(ClerkUserType.PROVIDER)
def accept_provider_invite(invite_id: str):
    user = get_current_user()

    if user is None or user.user_data.provider_id is None:
        abort(401)

    invitations = ProviderInvitation.invitations_by_id(invite_id)

    child_ids: list[int] = []
    for invitation in invitations:
        if invitation.accepted:
            abort(400, description="Invitation already accepted.")
        child_ids.append(int(invitation.child_google_sheet_id))

    child_data, family_data = get_invite_data(child_ids)

    provider_rows = get_providers()
    provider = get_row(provider_rows, user.user_data.provider_id)

    accept_request = send_provider_invite_accept_email(
        provider_name=provider.get(ProviderColumnNames.NAME),
        provider_id=provider.get(ProviderColumnNames.ID),
        parent_name=format_name(family_data),
        parent_id=family_data.get(FamilyColumnNames.ID),
        children=child_data,
    )

    if not accept_request:
        current_app.logger.error(
            f"Failed to send provider invite accept email for provider ID {user.user_data.provider_id} and family ID {family_data.get(FamilyColumnNames.ID)}.",
        )

    for invitation in invitations:
        invitation.record_accepted()

    db.session.add_all(invitations)
    db.session.commit()

    return jsonify({"message": "Success"}, 200)
