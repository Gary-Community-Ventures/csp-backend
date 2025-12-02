from datetime import date

from flask import Blueprint, jsonify, request

from app.auth.decorators import (
    ClerkUserType,
    auth_required,
)
from app.enums.care_day_type import CareDayType
from app.models.utils import get_care_day_cost
from app.schemas.care_day import AllocatedCareDayResponse

from ..extensions import db
from ..models import AllocatedCareDay, MonthAllocation

bp = Blueprint("care_day", __name__, url_prefix="/care-days")


@bp.route("", methods=["POST"])
@auth_required(ClerkUserType.FAMILY)
def create_care_day():
    data = request.get_json()
    allocation_id = data.get("allocation_id")
    provider_id = data.get("provider_id")
    care_date_str = data.get("date")
    day_type_str = data.get("type")

    if not all([allocation_id, provider_id, care_date_str, day_type_str]):
        return jsonify({"error": "Missing required fields"}), 400

    try:
        care_date = date.fromisoformat(care_date_str)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    try:
        day_type = CareDayType(day_type_str)
    except ValueError:
        return jsonify({"error": f"Invalid care day type: {day_type_str}"}), 400

    allocation = db.session.get(MonthAllocation, allocation_id)
    if not allocation:
        return jsonify({"error": "MonthAllocation not found"}), 404

    try:
        care_day = AllocatedCareDay.create_care_day(
            allocation=allocation,
            provider_id=provider_id,
            care_date=care_date,
            day_type=day_type,
        )
        return (
            jsonify(AllocatedCareDayResponse.model_validate(care_day).model_dump()),
            201,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/<int:care_day_id>", methods=["PUT"])
@auth_required(ClerkUserType.FAMILY)
def update_care_day(care_day_id):
    care_day = db.session.get(AllocatedCareDay, care_day_id)
    if not care_day:
        return jsonify({"error": "Care day not found"}), 404

    if care_day.is_locked:
        return jsonify({"error": "Cannot modify a locked care day"}), 403

    if care_day.is_submitted:
        return jsonify({"error": "Cannot modify a care day that has been submitted"}), 403

    data = request.get_json()
    day_type_str = data.get("type")

    if not day_type_str:
        return jsonify({"error": "Missing type field"}), 400

    try:
        new_day_type = CareDayType(day_type_str)
    except ValueError:
        return jsonify({"error": f"Invalid care day type: {day_type_str}"}), 400

    was_deleted = care_day.is_deleted

    if was_deleted:
        care_day.restore()

    if care_day.type != new_day_type or was_deleted:
        care_day.type = new_day_type

        new_amount_missing_cents = 0
        new_care_day_cost = get_care_day_cost(
            new_day_type,
            provider_id=care_day.provider_supabase_id,
            child_id=care_day.care_month_allocation.child_supabase_id,
        )

        total_remaining_cents = (
            care_day.amount_cents + care_day.care_month_allocation.remaining_unselected_cents
        )

        if total_remaining_cents < new_care_day_cost:
            new_amount_missing_cents = new_care_day_cost - total_remaining_cents
            new_care_day_cost = total_remaining_cents

        # If changing the type results in over-allocation, soft delete the care day
        # As that resets the day to the default empty state
        if new_care_day_cost <= 0:
            care_day.soft_delete()
            return jsonify(AllocatedCareDayResponse.model_validate(care_day).model_dump())
        else:
            care_day.amount_cents = new_care_day_cost
            care_day.amount_missing_cents = new_amount_missing_cents

    db.session.commit()
    db.session.refresh(care_day)

    return jsonify(AllocatedCareDayResponse.model_validate(care_day).model_dump())


@bp.route("/<int:care_day_id>", methods=["DELETE"])
@auth_required(ClerkUserType.FAMILY)
def delete_care_day(care_day_id):
    care_day = db.session.get(AllocatedCareDay, care_day_id)
    if not care_day:
        return jsonify({"error": "Care day not found"}), 404

    if care_day.is_locked:
        return jsonify({"error": "Cannot delete a locked care day"}), 403

    if care_day.is_submitted:
        return jsonify({"error": "Cannot delete a care day that has been submitted and paid"}), 403

    care_day.soft_delete()
    return "", 204
