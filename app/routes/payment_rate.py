from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from app.auth.decorators import ClerkUserType, auth_required
from app.auth.helpers import get_family_user, get_provider_user
from app.extensions import db
from app.models import PaymentRate
from app.schemas.payment_rate import (
    PaymentRateCreate,
    PaymentRateResponse,
)
from app.supabase.helpers import cols, unwrap_or_abort
from app.supabase.tables import Child, Family, Provider
from app.utils.email_service import send_new_payment_rate_email

bp = Blueprint("payment_rate_bp", __name__, url_prefix="/payment-rates")


@bp.post("/<child_id>")
@auth_required(ClerkUserType.PROVIDER)
def create_payment_rate(child_id: str):
    """Create a new payment rate for a given provider and child."""
    try:
        payment_rate_data = PaymentRateCreate(**request.get_json())
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    user = get_provider_user()
    provider_id = user.user_data.provider_id

    provider_result = Provider.select_by_id(cols(Provider.ID, Child.join(Child.ID)), int(provider_id)).execute()
    provider = unwrap_or_abort(provider_result)

    if provider is None:
        return jsonify({"error": "Provider not found"}), 404

    is_childs_provider = False
    for child in Child.unwrap(provider):
        if Child.ID(child) == child_id:
            is_childs_provider = True
            break

    if not is_childs_provider:
        return jsonify({"error": "Child not found"}), 404

    existing_rate = PaymentRate.get(provider_id=provider_id, child_id=child_id)

    if existing_rate:
        return (
            jsonify({"error": "Payment rate already exists for this provider and child"}),
            400,
        )

    payment_rate = PaymentRate.create(
        provider_id=provider_id,
        child_id=child_id,
        half_day_rate=payment_rate_data.half_day_rate_cents,
        full_day_rate=payment_rate_data.full_day_rate_cents,
    )

    send_new_payment_rate_email(
        provider_id=provider_id,
        child_id=child_id,
        half_day_rate_cents=payment_rate_data.half_day_rate_cents,
        full_day_rate_cents=payment_rate_data.full_day_rate_cents,
    )

    db.session.add(payment_rate)
    db.session.commit()

    return jsonify(PaymentRateResponse.model_validate(payment_rate).model_dump()), 201


@bp.get("/<string:provider_id>/<string:child_id>")
@auth_required(ClerkUserType.FAMILY)
def get_payment_rate(provider_id, child_id):
    """Get a payment rate for a given provider and child."""
    user = get_family_user()
    family_id = user.user_data.family_id

    child_result = Child.select_by_id(
        cols(Child.ID, Family.join(Family.ID), Provider.join(Provider.ID)), int(child_id)
    ).execute()
    child = unwrap_or_abort(child_result)

    if child is None:
        return jsonify({"error": "Child not found"}), 404

    if child.family_id != family_id:
        return jsonify({"error": "Child not found"}), 404

    child_has_provider = False
    for provider in Provider.unwrap(child):
        if Provider.ID(provider) == provider_id:
            child_has_provider = True
            break

    if not child_has_provider:
        return jsonify({"error": "Provider not found"}), 404

    payment_rate = PaymentRate.get(provider_id=provider_id, child_id=child_id)
    if not payment_rate:
        return jsonify({"error": "Payment rate not found"}), 404

    return jsonify(PaymentRateResponse.model_validate(payment_rate).model_dump()), 200
