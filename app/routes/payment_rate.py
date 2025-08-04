from flask import Blueprint, request, jsonify
from app.models import PaymentRate
from app.extensions import db
from app.auth.decorators import auth_required, ClerkUserType
from app.schemas.payment_rate import PaymentRateResponse, PaymentRateCreate, PaymentRateUpdate
from pydantic import ValidationError

payment_rate_bp = Blueprint("payment_rate_bp", __name__, url_prefix="/payment-rates")


@payment_rate_bp.route("", methods=["POST"])
@auth_required(ClerkUserType.FAMILY)
def create_payment_rate():
    """Create a new payment rate for a given provider and child."""
    try:
        payment_rate_data = PaymentRateCreate(**request.get_json())
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    existing_rate = PaymentRate.get(provider_id=payment_rate_data.google_sheets_provider_id, child_id=payment_rate_data.google_sheets_child_id)
    if existing_rate:
        return jsonify({"error": "Payment rate already exists for this provider and child"}), 400

    payment_rate = PaymentRate.create(
        provider_id=payment_rate_data.google_sheets_provider_id,
        child_id=payment_rate_data.google_sheets_child_id,
        half_day_rate=payment_rate_data.half_day_rate_cents,
        full_day_rate=payment_rate_data.full_day_rate_cents,
    )

    return jsonify(PaymentRateResponse.model_validate(payment_rate).model_dump()), 201


@payment_rate_bp.route("/<int:provider_id>/<int:child_id>", methods=["GET"])
@auth_required(ClerkUserType.FAMILY)
def get_payment_rate(provider_id, child_id):
    """Get a payment rate for a given provider and child."""
    payment_rate = PaymentRate.get(provider_id=provider_id, child_id=child_id)
    if not payment_rate:
        return jsonify({"error": "Payment rate not found"}), 404

    return jsonify(PaymentRateResponse.model_validate(payment_rate).model_dump()), 200


@payment_rate_bp.route("/<int:provider_id>/<int:child_id>", methods=["PUT"])
@auth_required(ClerkUserType.FAMILY)
def update_payment_rate(provider_id, child_id):
    """Update a payment rate for a given provider and child."""
    payment_rate = PaymentRate.get(provider_id=provider_id, child_id=child_id)
    if not payment_rate:
        return jsonify({"error": "Payment rate not found"}), 404

    try:
        payment_rate_data = PaymentRateUpdate(**request.get_json())
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    if payment_rate_data.half_day_rate_cents is not None:
        payment_rate.half_day_rate_cents = payment_rate_data.half_day_rate_cents
    if payment_rate_data.full_day_rate_cents is not None:
        payment_rate.full_day_rate_cents = payment_rate_data.full_day_rate_cents

    db.session.commit()

    return jsonify(PaymentRateResponse.model_validate(payment_rate).model_dump()), 200
