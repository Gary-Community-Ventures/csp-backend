from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from app.auth.decorators import ClerkUserType, auth_required
from app.auth.helpers import get_current_user
from app.extensions import db
from app.models import LinkClickTrack
from app.schemas.link_click import (
    LinkClickCreate,
    LinkClickGetArgs,
    LinkClickResponse,
)

bp = Blueprint("link_click_bp", __name__)


def _get_existing_click(provider_id: str | None, family_id: str | None, link: str) -> LinkClickTrack | None:
    existing_click = None
    if provider_id:
        existing_click = LinkClickTrack.get_by_provider(provider_id=provider_id, link=link)
    if family_id and not existing_click:
        existing_click = LinkClickTrack.get_by_family(family_id=family_id, link=link)
    return existing_click


@bp.post("/click-link")
@auth_required(ClerkUserType.NONE)
def create_link_click():
    """Create a new link click record."""
    try:
        link_click_data = LinkClickCreate(**request.get_json())
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    user = get_current_user()
    provider_id = user.user_data.provider_id
    family_id = user.user_data.family_id

    if provider_id is None and family_id is None:
        return jsonify({"error": "User must be associated with either a provider or a family"}), 400

    if existing_click := _get_existing_click(provider_id, family_id, link_click_data.link):
        existing_click.click_count += 1
        db.session.commit()
        return jsonify(LinkClickResponse.model_validate(existing_click).model_dump()), 200

    link_click = LinkClickTrack.create(
        provider_supabase_id=provider_id,
        family_supabase_id=family_id,
        link=link_click_data.link,
    )
    db.session.add(link_click)
    db.session.commit()

    return jsonify(LinkClickResponse.model_validate(link_click).model_dump()), 201


@bp.get("/click-link")
@auth_required(ClerkUserType.NONE)
def get_link_clicked():
    """Get the link click record."""
    # Get url parameter
    try:
        link_click_data = LinkClickGetArgs(**request.args)
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    user = get_current_user()
    provider_id = user.user_data.provider_id
    family_id = user.user_data.family_id

    if provider_id is None and family_id is None:
        return jsonify({"error": "User must be associated with either a provider or a family"}), 400

    if existing_click := _get_existing_click(provider_id, family_id, link_click_data.link):
        return jsonify(LinkClickResponse.model_validate(existing_click).model_dump()), 200

    return jsonify({"error": "Link click record not found"}), 404
