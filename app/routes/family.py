from clerk_backend_api import Clerk, CreateInvitationRequestBody
from flask import Blueprint, abort, jsonify, request, current_app

from app.extensions import db
from app.models.family import Family

from app.auth.decorators import ClerkUserType, auth_required
from app.auth.helpers import get_current_user
from app.sheets.mappings import (
    CaregiverColumnNames,
    ChildColumnNames,
    TransactionColumnNames,
    get_caregiver_child_mapping_caregiver,
    get_caregiver_child_mappings,
    get_caregivers,
    get_child,
    get_child_caregivers,
    get_children,
    get_family,
    get_families,
    get_child_transactions,
    get_family_children,
    get_transactions,
)


bp = Blueprint("family", __name__)


# TODO: add api key
@bp.post("/family")
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
    family = Family.from_dict(data)
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


@bp.get("/family")
@auth_required(ClerkUserType.FAMILY)
def family_data():
    user = get_current_user()

    if user is None or user.user_data.family_id is None:
        abort(401)

    family_id = user.user_data.family_id
    active_child_id = 2  # FIXME: get the actual child id

    family_rows = get_families()
    child_rows = get_children()
    caregiver_child_mapping_rows = get_caregiver_child_mappings()
    caregiver_rows = get_caregivers()
    transaction_rows = get_transactions()

    family_data = get_family(family_id, family_rows)
    child_data = get_child(active_child_id, child_rows)
    family_children = get_family_children(family_id, child_rows)
    caregiver_data = get_child_caregivers(active_child_id, caregiver_child_mapping_rows, caregiver_rows)
    transaction_data = get_child_transactions(active_child_id, caregiver_child_mapping_rows, transaction_rows)

    selected_child_info = {
        "id": child_data.get(ChildColumnNames.ID),
        "first_name": child_data.get(ChildColumnNames.FIRST_NAME),
        "last_name": child_data.get(ChildColumnNames.LAST_NAME),
        "balance": child_data.get(ChildColumnNames.BALANCE),
    }

    caregivers = [
        {
            "id": c.get(CaregiverColumnNames.ID),
            "name": c.get(CaregiverColumnNames.NAME),
            "status": c.get(CaregiverColumnNames.STATUS).lower(),
        }
        for c in caregiver_data
    ]

    transactions = [
        {
            "id": t.get(TransactionColumnNames.ID),
            "name": get_caregiver_child_mapping_caregiver(
                t.get(TransactionColumnNames.CAREGIVER_CHILD_ID), caregiver_child_mapping_rows, caregiver_rows
            ).get(CaregiverColumnNames.NAME),
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
            "caregivers": caregivers,
            "transactions": transactions,
            "children": children,
        }
    )
