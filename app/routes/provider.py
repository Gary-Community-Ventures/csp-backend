from clerk_backend_api import Clerk, CreateInvitationRequestBody
from flask import Blueprint, abort, jsonify, request, current_app
from app.auth.helpers import get_current_user
from app.extensions import db
from app.models import Provider, AllocatedCareDay, MonthAllocation
from app.auth.decorators import ClerkUserType, auth_required, api_key_required
from app.sheets.mappings import (
    ChildColumnNames,
    ProviderColumnNames,
    TransactionColumnNames,
    get_children,
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

bp = Blueprint("provider", __name__, url_prefix='/api/provider')


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
            email_address=data["email"], redirect_url=f"{fe_domain}/auth/sign-up", public_metadata=meta_data
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
            t.get(TransactionColumnNames.PROVIDER_CHILD_ID), provider_child_mapping_rows, child_rows
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


@bp.route('/<int:provider_id>/allocated_care_days', methods=['GET'])
@auth_required(ClerkUserType.PROVIDER)
def get_allocated_care_days(provider_id):
    child_id = request.args.get('childId', type=int)
    start_date_str = request.args.get('startDate')
    end_date_str = request.args.get('endDate')

    query = AllocatedCareDay.query.filter_by(provider_google_sheets_id=provider_id)

    if child_id:
        query = query.join(MonthAllocation).filter(MonthAllocation.google_sheets_child_id == child_id)

    if start_date_str:
        try:
            start_date = date.fromisoformat(start_date_str)
            query = query.filter(AllocatedCareDay.date >= start_date)
        except ValueError:
            return jsonify({'error': 'Invalid startDate format. Use YYYY-MM-DD.'}), 400

    if end_date_str:
        try:
            end_date = date.fromisoformat(end_date_str)
            query = query.filter(AllocatedCareDay.date <= end_date)
        except ValueError:
            return jsonify({'error': 'Invalid endDate format. Use YYYY-MM-DD.'}), 400

    care_days = query.all()

    # Group by child
    care_days_by_child = defaultdict(list)
    for day in care_days:
        care_days_by_child[day.care_month_allocation.google_sheets_child_id].append(day.to_dict())

    return jsonify(care_days_by_child)
