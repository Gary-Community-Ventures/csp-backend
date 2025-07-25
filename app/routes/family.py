from typing import Optional
from clerk_backend_api import Clerk, CreateInvitationRequestBody
from flask import Blueprint, abort, jsonify, request, current_app
from app.extensions import db
from app.models.family import Family
from app.auth.decorators import ClerkUserType, auth_required, api_key_required
from app.auth.helpers import get_current_user
from app.sheets.mappings import (
    ProviderColumnNames,
    ChildColumnNames,
    TransactionColumnNames,
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

    family_id = user.user_data.family_id  # TODO: Get Google Sheet ID from DB
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

    family_id = user.user_data.family_id  # TODO: Get Google Sheet ID from DB
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
