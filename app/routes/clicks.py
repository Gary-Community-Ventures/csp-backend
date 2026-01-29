from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from app.auth.decorators import ClerkUserType, auth_required
from app.auth.helpers import get_current_user
from app.extensions import db
from app.models import Click
from app.schemas.click import (
    ClickCreate,
    ClickGetQuery,
    ClickResponse,
)

bp = Blueprint("click_bp", __name__)


def _get_existing_click(provider_id: str | None, family_id: str | None, url: str) -> Click | None:
    existing_click = None
    if provider_id:
        existing_click = Click.get_by_provider(provider_id=provider_id, url=url)
    if family_id and not existing_click:
        existing_click = Click.get_by_family(family_id=family_id, url=url)
    return existing_click


@bp.post("/clicks")
@auth_required(ClerkUserType.NONE)
def create_click():
    """Create a new click record or update click count of existing record."""
    try:
        click_data = ClickCreate(**request.get_json())
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    user = get_current_user()
    provider_id = user.user_data.provider_id
    family_id = user.user_data.family_id

    if provider_id is None and family_id is None:
        return jsonify({"error": "User must be associated with either a provider or a family"}), 400

    if existing_click := _get_existing_click(provider_id, family_id, click_data.tracking_id):
        existing_click.click_count += 1
        db.session.commit()
        return jsonify(ClickResponse.model_validate(existing_click).model_dump()), 200

    click = Click.create(
        provider_id=provider_id,
        family_id=family_id,
        tracking_id=click_data.tracking_id,
    )
    db.session.add(click)
    db.session.commit()

    return jsonify(ClickResponse.model_validate(click).model_dump()), 201


@bp.get("/clicks")
@auth_required(ClerkUserType.NONE)
def get_click_record():
    """Get the click record."""
    # Get url parameter
    try:
        click_data = ClickGetQuery(**request.args)
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    user = get_current_user()
    provider_id = user.user_data.provider_id
    family_id = user.user_data.family_id

    if provider_id is None and family_id is None:
        return jsonify({"error": "User must be associated with either a provider or a family"}), 400

    if existing_click := _get_existing_click(provider_id, family_id, click_data.tracking_id):
        return jsonify(ClickResponse.model_validate(existing_click).model_dump()), 200

    return jsonify({"error": "click record not found"}), 404
