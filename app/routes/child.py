from flask import Blueprint, jsonify, request
from app.extensions import db
from app.models import MonthAllocation, AllocatedCareDay
from app.auth.decorators import (
    ClerkUserType,
    auth_required,
)
from app.utils.email_service import send_submission_notification

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

    return jsonify(
        {
            "message": "Submission successful",
            "new_days": [day.to_dict() for day in new_days],
            "modified_days": [day.to_dict() for day in modified_days],
            "removed_days": [day.to_dict() for day in removed_days],
        }
    )