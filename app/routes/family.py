from typing import Optional
from clerk_backend_api import Clerk, CreateInvitationRequestBody
from flask import Blueprint, abort, jsonify, request, current_app
from app.data.providers.mappings import ProviderListColumnNames
from app.extensions import db
from app.models import Family, MonthAllocation, AllocatedCareDay
from app.auth.decorators import (
    ClerkUserType,
    auth_required,
    api_key_required,
)
from app.auth.helpers import get_current_user
from app.sheets.helpers import KeyMap, get_row
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
<<<<<<< HEAD
from datetime import date
from ..utils.email_service import send_submission_notification
=======
from app.utils.email_service import send_add_licensed_provider_email
>>>>>>> dev

bp = Blueprint("family", __name__, url_prefix='/api/family')


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
        "types": [
            ClerkUserType.FAMILY
        ],  # NOTE: list in case we need to have people who fit into multiple categories
        "family_id": family.id,
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
    provider_data = get_child_providers(
        active_child_id, provider_child_mapping_rows, provider_rows
    )
    transaction_data = get_child_transactions(
        active_child_id, provider_child_mapping_rows, transaction_rows
    )

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

    return jsonify(
        {
            "selected_child_info": selected_child_info,
            "providers": providers,
            "transactions": transactions,
            "children": children,
            "is_also_provider": ClerkUserType.PROVIDER.value in user.user_data.types,
        }
    )


@bp.route(
    "/<int:family_id>/child/<int:child_id>/allocation/<int:month>/<int:year>",
    methods=["GET"],
)
@auth_required(ClerkUserType.FAMILY)
def get_month_allocation(family_id, child_id, month, year):
    provider_id = request.args.get("provider_id", type=int)
    if not provider_id:
        return jsonify({"error": "provider_id query parameter is required"}), 400

    try:
        month_date = date(year, month, 1)
    except ValueError:
        return jsonify({"error": "Invalid month or year"}), 400

    allocation = MonthAllocation.get_or_create_for_month(child_id, month_date)

    care_days_query = AllocatedCareDay.query.filter_by(
        care_month_allocation_id=allocation.id, provider_google_sheets_id=provider_id
    )
    care_days = care_days_query.all()

    def get_submission_status(day):
        if day.is_deleted:
            return "deleted"
        if day.is_new_since_submission:
            return "new"
        if day.needs_resubmission:
            return "needs_resubmission"
        if day.needs_resubmission:
            return "needs_resubmission"
        return "submitted"

    return jsonify(
        {
            "total_dollars": allocation.allocation_dollars,
            "used_dollars": allocation.used_dollars,
            "remaining_dollars": allocation.remaining_dollars,
            "total_days": allocation.allocation_days,
            "used_days": allocation.used_days,
            "remaining_days": allocation.remaining_days,
            "care_days": [
                {**day.to_dict(), "status": get_submission_status(day)}
                for day in care_days
            ],
        }
    )


@bp.route(
    "/<int:family_id>/child/<int:child_id>/provider/<int:provider_id>/allocation/<int:month>/<int:year>/submit",
    methods=["POST"],
)
@auth_required(ClerkUserType.FAMILY)
def submit_care_days(family_id, child_id, provider_id, month, year):
    try:
        month_date = date(year, month, 1)
    except ValueError:
        return jsonify({"error": "Invalid month or year"}), 400

    allocation = MonthAllocation.query.filter_by(
        google_sheets_child_id=child_id, date=month_date
    ).first()
    if not allocation:
        return jsonify({"error": "Allocation not found"}), 404

    care_days_to_submit = AllocatedCareDay.query.filter(
        AllocatedCareDay.care_month_allocation_id == allocation.id,
        AllocatedCareDay.provider_google_sheets_id == provider_id,
        AllocatedCareDay.deleted_at.is_(None),  # Don't submit deleted days
    ).all()

    new_days = [day for day in care_days_to_submit if day.is_new_since_submission]
    modified_days = [
        day
        for day in care_days_to_submit
        if day.needs_resubmission and not day.is_new_since_submission
    ]
    removed_days = AllocatedCareDay.query.filter(
        AllocatedCareDay.care_month_allocation_id == allocation.id,
        AllocatedCareDay.provider_google_sheets_id == provider_id,
        AllocatedCareDay.deleted_at.isnot(None),
    ).all()

    # Send email notification
    # This is a placeholder for the actual email sending logic
    send_submission_notification(
        provider_id, child_id, new_days, modified_days, removed_days
    )

    for day in care_days_to_submit:
        day.mark_as_submitted()
    db.session.commit()

    return jsonify(
        {
            "message": "Submission successful",
            "new_days": [day.to_dict() for day in new_days],
            "modified_days": [day.to_dict() for day in modified_days],
            "removed_days": [day.to_dict() for day in removed_days],
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

    family_id = user.user_data.family_id  # TODO: Get Google Sheet ID from DB

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
        parent_name=family.get(FamilyColumnNames.FIRST_NAME) + " " + family.get(FamilyColumnNames.LAST_NAME),
        parent_id=family.get(FamilyColumnNames.ID),
        children=children,
    )

    return jsonify({"message": "Success"}, 201)
