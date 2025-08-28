from datetime import date

from flask import Blueprint, jsonify, request

from app.auth.decorators import (
    ClerkUserType,
    auth_required,
)
from app.extensions import db
from app.models import AllocatedCareDay, MonthAllocation
from app.schemas.care_day import AllocatedCareDayResponse
from app.schemas.month_allocation import (
    MonthAllocationResponse,
)
from app.sheets.mappings import (
    ChildColumnNames,
    ProviderColumnNames,
    get_child,
    get_children,
    get_provider,
    get_providers,
)
from app.utils.email_service import send_submission_notification
from app.utils.json_utils import custom_jsonify

bp = Blueprint("child", __name__)


@bp.route(
    "/child/<string:child_id>/allocation/<int:month>/<int:year>",
    methods=["GET"],
)
@auth_required(ClerkUserType.FAMILY)
def get_month_allocation(child_id, month, year):
    provider_id = request.args.get("provider_id")
    try:
        month_date = date(year, month, 1)
        allocation = MonthAllocation.get_or_create_for_month(child_id, month_date)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if provider_id:
        care_days_query = AllocatedCareDay.query.filter_by(
            care_month_allocation_id=allocation.id,
            provider_google_sheets_id=provider_id,
        )
    else:
        care_days_query = AllocatedCareDay.query.filter_by(care_month_allocation_id=allocation.id)
    care_days = care_days_query.all()

    # Serialize care_days using Pydantic model
    serialized_care_days = []
    for day in care_days:
        care_day_data = AllocatedCareDayResponse.model_validate(day).model_dump()
        serialized_care_days.append(care_day_data)

    # Serialize allocation using MonthAllocationResponse
    serialized_allocation = MonthAllocationResponse.model_validate(allocation).model_dump()
    serialized_allocation["care_days"] = serialized_care_days

    return custom_jsonify(serialized_allocation)


@bp.route(
    "/child/<string:child_id>/provider/<string:provider_id>/allocation/<int:month>/<int:year>/submit",
    methods=["POST"],
)
@auth_required(ClerkUserType.FAMILY)
def submit_care_days(child_id, provider_id, month, year):
    try:
        month_date = date(year, month, 1)
    except ValueError:
        return jsonify({"error": "Invalid month or year"}), 400

    allocation = MonthAllocation.query.filter_by(google_sheets_child_id=child_id, date=month_date).first()
    if not allocation:
        return jsonify({"error": "Allocation not found"}), 404

    if allocation.over_allocation:
        return jsonify({"error": "Cannot submit: allocation exceeded"}), 400

    # Get child data to find the family ID
    child_data = get_child(child_id, get_children())
    if not child_data:
        return jsonify({"error": "Child not found"}), 404

    if not child_data.get(ChildColumnNames.PAYMENT_ENABLED):
        return jsonify({"error": "Cannot submit: family payment not enabled"}), 400

    provider_data = get_provider(provider_id, get_providers())
    if not provider_data:
        return jsonify({"error": "Provider not found"}), 404

    if not provider_data.get(ProviderColumnNames.PAYMENT_ENABLED):
        return jsonify({"error": "Cannot submit: provider payment not enabled"}), 400

    care_days_to_submit = AllocatedCareDay.query.filter(
        AllocatedCareDay.care_month_allocation_id == allocation.id,
        AllocatedCareDay.provider_google_sheets_id == provider_id,
        AllocatedCareDay.deleted_at.is_(None),  # Don't submit deleted days
    ).all()

    new_days = [day for day in care_days_to_submit if day.is_new]
    modified_days = [day for day in care_days_to_submit if day.needs_resubmission and not day.is_new]

    removed_days = AllocatedCareDay.query.filter(
        AllocatedCareDay.care_month_allocation_id == allocation.id,
        AllocatedCareDay.provider_google_sheets_id == provider_id,
        AllocatedCareDay.deleted_at.isnot(None),
    ).all()
    removed_days_where_delete_not_submitted = [day for day in removed_days if day.delete_not_submitted]

    # Send email notification
    send_submission_notification(
        provider_id=provider_id,
        child_id=child_id,
        new_days=new_days,
        modified_days=modified_days,
        removed_days=removed_days_where_delete_not_submitted,
    )

    for day in care_days_to_submit:
        day.mark_as_submitted()
    db.session.commit()

    for day in removed_days_where_delete_not_submitted:
        day.last_submitted_at = None  # Reset last submitted date for deleted days
    db.session.commit()

    return jsonify(
        {
            "message": "Submission successful",
            "new_days": [AllocatedCareDayResponse.model_validate(day).model_dump() for day in new_days],
            "modified_days": [AllocatedCareDayResponse.model_validate(day).model_dump() for day in modified_days],
            "removed_days": [
                AllocatedCareDayResponse.model_validate(day).model_dump()
                for day in removed_days_where_delete_not_submitted
            ],
        }
    )
