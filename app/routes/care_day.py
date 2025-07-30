from flask import Blueprint, jsonify, request
from ..models import AllocatedCareDay, MonthAllocation
from ..extensions import db
from datetime import date

from app.auth.decorators import (
    ClerkUserType,
    auth_required,
)

bp = Blueprint('care_day', __name__, url_prefix='/api/care-days')

@bp.route('', methods=['POST'])
@auth_required(ClerkUserType.FAMILY)
def create_care_day():
    data = request.get_json()
    allocation_id = data.get('allocation_id')
    provider_id = data.get('provider_id')
    care_date_str = data.get('date')
    day_type = data.get('type')

    if not all([allocation_id, provider_id, care_date_str, day_type]):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        care_date = date.fromisoformat(care_date_str)
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400

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
        return jsonify(care_day.to_dict()), 201
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
    new_type = data.get('type')

    if not new_type:
        return jsonify({'error': 'Missing type field'}), 400

    care_day.type = new_type
    db.session.commit()

    return jsonify(care_day.to_dict())

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