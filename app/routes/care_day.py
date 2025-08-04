from flask import Blueprint, jsonify, request
from ..models import AllocatedCareDay, MonthAllocation
from ..extensions import db
from datetime import date, datetime

from app.auth.decorators import (
    ClerkUserType,
    auth_required,
)
from app.schemas.care_day import AllocatedCareDayResponse # Import the Pydantic model
from app.enums.care_day_type import CareDayType
from app.models.utils import get_care_day_cost # Import get_care_day_cost

bp = Blueprint('care_day', __name__, url_prefix='/care-days')

@bp.route('', methods=['POST'])
@auth_required(ClerkUserType.FAMILY)
def create_care_day():
    data = request.get_json()
    allocation_id = data.get('allocation_id')
    provider_id = data.get('provider_id')
    care_date_str = data.get('date')
    day_type_str = data.get('type')

    if not all([allocation_id, provider_id, care_date_str, day_type_str]):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        care_date = date.fromisoformat(care_date_str)
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400

    try:
        day_type = CareDayType(day_type_str)
    except ValueError:
        return jsonify({'error': f'Invalid care day type: {day_type_str}'}), 400

    allocation = MonthAllocation.query.get(allocation_id)
    if not allocation:
        return jsonify({'error': 'MonthAllocation not found'}), 404

    try:
        care_day = AllocatedCareDay.create_care_day(
            allocation=allocation,
            provider_id=provider_id,
            care_date=care_date,
            day_type=day_type
        )
        return jsonify(AllocatedCareDayResponse.from_orm(care_day).model_dump()), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

@bp.route('/<int:care_day_id>', methods=['PUT'])
@auth_required(ClerkUserType.FAMILY)
def update_care_day(care_day_id):
    care_day = AllocatedCareDay.query.get(care_day_id)
    if not care_day:
        return jsonify({'error': 'Care day not found'}), 404

    if care_day.is_locked:
        return jsonify({'error': 'Cannot modify a locked care day'}), 403

    data = request.get_json()
    day_type_str = data.get('type')

    if not day_type_str:
        return jsonify({'error': 'Missing type field'}), 400

    try:
        new_day_type = CareDayType(day_type_str)
    except ValueError:
        return jsonify({'error': f'Invalid care day type: {day_type_str}'}), 400
    
    if care_day.is_locked:
        return jsonify({'error': 'Cannot modify a locked care day'}), 403

    was_deleted = care_day.is_deleted

    if was_deleted:
        care_day.restore()

    if care_day.type != new_day_type or was_deleted:
        print(f"Updating care day {care_day_id} from type {care_day.type} to {new_day_type}")
        care_day.type = new_day_type
        care_day.amount_cents = get_care_day_cost(
            new_day_type,
            provider_id=care_day.provider_google_sheets_id,
            child_id=care_day.care_month_allocation.google_sheets_child_id,
        )

    db.session.commit()
    db.session.refresh(care_day)
    
    return jsonify(AllocatedCareDayResponse.from_orm(care_day).model_dump())

@bp.route('/<int:care_day_id>', methods=['DELETE'])
@auth_required(ClerkUserType.FAMILY)
def delete_care_day(care_day_id):
    care_day = AllocatedCareDay.query.get(care_day_id)
    if not care_day:
        return jsonify({'error': 'Care day not found'}), 404

    if care_day.is_locked:
        return jsonify({'error': 'Cannot delete a locked care day'}), 403

    care_day.soft_delete()
    return '', 204