from flask import Blueprint, request, jsonify
from app.models import PaymentRate
from app.extensions import db
from app.auth.decorators import auth_required, ClerkUserType
from app.schemas.payment_rate import PaymentRateResponse

payment_rate_bp = Blueprint("payment_rate_bp", __name__, url_prefix="/payment-rates")


@payment_rate_bp.route("", methods=["POST"])
@auth_required(ClerkUserType.FAMILY)
def create_payment_rate():
    """Create a new payment rate for a given provider and child."""
    data = request.get_json()
    provider_id = data.get("provider_id")
    child_id = data.get("child_id")
    half_day_rate = data.get("half_day_rate")
    full_day_rate = data.get("full_day_rate")

    if not all([provider_id, child_id, half_day_rate, full_day_rate]):
        return jsonify({"error": "Missing required fields"}), 400

    existing_rate = PaymentRate.get(provider_id=provider_id, child_id=child_id)
    if existing_rate:
        return jsonify({"error": "Payment rate already exists for this provider and child"}), 400

    payment_rate = PaymentRate.create(
        provider_id=provider_id,
        child_id=child_id,
        half_day_rate=half_day_rate,
        full_day_rate=full_day_rate,
    )

    return jsonify(PaymentRateResponse.from_orm(payment_rate).model_dump()), 201


@payment_rate_bp.route("/<int:provider_id>/<int:child_id>", methods=["GET"])
@auth_required(ClerkUserType.FAMILY)
def get_payment_rate(provider_id, child_id):
    """Get a payment rate for a given provider and child."""
    payment_rate = PaymentRate.get(provider_id=provider_id, child_id=child_id)
    if not payment_rate:
        return jsonify({"error": "Payment rate not found"}), 404

    return jsonify(PaymentRateResponse.from_orm(payment_rate).model_dump()), 200


@payment_rate_bp.route("/<int:provider_id>/<int:child_id>", methods=["PUT"])
@auth_required(ClerkUserType.FAMILY)
def update_payment_rate(provider_id, child_id):
    """Update a payment rate for a given provider and child."""
    payment_rate = PaymentRate.get(provider_id=provider_id, child_id=child_id)
    if not payment_rate:
        return jsonify({"error": "Payment rate not found"}), 404

    data = request.get_json()
    half_day_rate = data.get("half_day_rate")
    full_day_rate = data.get("full_day_rate")

    if half_day_rate:
        payment_rate.half_day_rate_cents = half_day_rate
    if full_day_rate:
        payment_rate.full_day_rate_cents = full_day_rate

    db.session.commit()

    return jsonify(PaymentRateResponse.from_orm(payment_rate).model_dump()), 200
