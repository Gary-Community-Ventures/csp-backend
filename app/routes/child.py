from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import MonthAllocation, AllocatedCareDay
from app.auth.decorators import (
    ClerkUserType,
    auth_required,
)
from app.utils.email_service import send_submission_notification
from app.schemas.care_day import AllocatedCareDayResponse # Import the Pydantic model
from app.schemas.month_allocation import MonthAllocationResponse # Import the MonthAllocationResponse
from app.utils.json_utils import custom_jsonify


from datetime import date


bp = Blueprint("child", __name__)


@bp.route(
    "/child/<int:child_id>/allocation/<int:month>/<int:year>",
    methods=["GET"],
)
@auth_required(ClerkUserType.FAMILY)
def get_month_allocation(child_id, month, year):
    provider_id = request.args.get("provider_id", type=int)
    if not provider_id:
        return jsonify({"error": "provider_id query parameter is required"}), 400

    try:
        month_date = date(year, month, 1)
        allocation = MonthAllocation.get_or_create_for_month(child_id, month_date)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    care_days_query = AllocatedCareDay.query.filter_by(
        care_month_allocation_id=allocation.id, provider_google_sheets_id=provider_id
    )
    care_days = care_days_query.all()

    # Serialize care_days using Pydantic model
    serialized_care_days = []
    for day in care_days:
        care_day_data = AllocatedCareDayResponse.from_orm(day).model_dump()
        serialized_care_days.append(care_day_data)

    # Serialize allocation using MonthAllocationResponse
    serialized_allocation = MonthAllocationResponse.from_orm(allocation).model_dump()
    serialized_allocation["care_days"] = serialized_care_days

    return custom_jsonify(serialized_allocation)


@bp.route(
    "/child/<int:child_id>/provider/<int:provider_id>/allocation/<int:month>/<int:year>/submit",
    methods=["POST"],
)
@auth_required(ClerkUserType.FAMILY)
def submit_care_days(child_id, provider_id, month, year):
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

    for day in removed_days:
        day.mark_as_submitted()
    db.session.commit()

    return jsonify(
        {
            "message": "Submission successful",
            "new_days": [AllocatedCareDayResponse.from_orm(day).model_dump() for day in new_days],
            "modified_days": [AllocatedCareDayResponse.from_orm(day).model_dump() for day in modified_days],
            "removed_days": [AllocatedCareDayResponse.from_orm(day).model_dump() for day in removed_days],
        }
    )