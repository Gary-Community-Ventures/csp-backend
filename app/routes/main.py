import traceback
from dataclasses import asdict

from flask import Blueprint, current_app, jsonify, request

from app.auth.decorators import (
    api_key_required,
)
from app.auth.helpers import get_current_user
from app.integrations.chek.schemas import (
    ACHFundingSource,
    ACHPaymentRequest,
    ACHPaymentType,
    CardCreateRequest,
    CardDetails,
    FlowDirection,
    TransferBalanceRequest,
)
from app.jobs.example_job import example_call_job_from_function

bp = Blueprint("main", __name__)


# Health check endpoint
@bp.route("/health")
def health():
    db_status = "disconnected"
    try:
        # Access db from current_app context
        with current_app.extensions["sqlalchemy"].engine.connect() as con:
            con.execute(current_app.extensions["sqlalchemy"].text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"failed: {e}"

    clerk_status = "not initialized"
    if hasattr(current_app, "clerk_client") and current_app.clerk_client is not None:
        clerk_status = "initialized"

    return (
        jsonify(
            {
                "status": "healthy",
                "message": "Flask backend is running",
                "database": db_status,
                "clerk_sdk": clerk_status,
                "version": current_app.config.get("APP_VERSION", "unknown"),
                "environment": current_app.config.get("FLASK_ENV", "unknown"),
            }
        ),
        200,
    )


# Basic route
@bp.route("/")
def index():
    return jsonify(
        {
            "message": "Flask backend API",
            "version": current_app.config.get("APP_VERSION", "unknown"),
        }
    )


# Sentry Test Route (for demonstration purposes, remove in production)
@bp.route("/sentry-test")
@api_key_required
def sentry_test():
    _ = 1 / 0
    return "This should not be reached if Sentry captures the error."


# Database Sentry Test Route (for demonstration purposes, remove in production)
@bp.route("/sentry-db-test")
@api_key_required
def sentry_db_test():
    try:
        # Access db from current_app context
        current_app.extensions["sqlalchemy"].session.execute(
            current_app.extensions["sqlalchemy"].text("SELECT non_existent_column FROM users")
        )
        current_app.extensions["sqlalchemy"].session.commit()
    except Exception as e:
        print(f"Database error occurred: {e}")
        return jsonify({"message": f"Database error triggered: {e}"}), 500
    return (
        jsonify({"message": ("Database operation attempted ", "(might have failed and been captured by Sentry)")}),
        200,
    )


@bp.route("/jobs/<job_id>/status", methods=["GET"])
@api_key_required
def job_status(job_id):
    status = current_app.extensions["job_manager"].get_job_status(job_id)
    if status is None:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(asdict(status))


@bp.route("/jobs/<job_id>/retry", methods=["POST"])
@api_key_required
def retry_job(job_id):
    result = current_app.extensions["job_manager"].retry_failed_job(job_id)
    return jsonify(asdict(result))


@bp.route("/jobs/queue-info", methods=["GET"])
@api_key_required
def queue_info():
    info = current_app.extensions["job_manager"].get_queue_info()
    if info is None:
        return jsonify({"error": "Queue not found"}), 404
    return jsonify(asdict(info))


@bp.route("/example-job", methods=["POST"])
@api_key_required
def example_job():
    current_app.logger.info("Enqueuing example job...")

    user = get_current_user()

    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400
    data = request.json
    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Missing or invalid JSON body"}), 400

    try:
        example_call_job_from_function(
            user_id=user.id if user else None,
            delay_seconds=data.get("delay_seconds", 0),
            sleep_time=data.get("sleep_time", 0),
            from_info="example_job_endpoint",
        )
        current_app.logger.info("Example job enqueued")
        return jsonify({"message": "Example job enqueued"}), 202
    except Exception as e:
        current_app.logger.error(f"Failed to enqueue example job: {e}")
        return jsonify({"error": f"Failed to enqueue example job: {str(e)}"}), 500


@bp.route("/test-chek", methods=["GET"])
def test_chek():
    """An endpoint to test the Chek integration."""
    try:
        chek_service = current_app.chek_service

        # --- Test: Create Card ---
        test_user_id = 750039  # As requested by the user
        test_amount = 0  # 10.00 USD in cents

        card_details = CardDetails(
            funding_method="wallet",  # Default from docs
            source_id=test_user_id,  # Assuming source_id is user_id for wallet funding
            amount=test_amount,
        )
        card_request = CardCreateRequest(user_id=test_user_id, card_details=card_details)

        new_card = chek_service.create_card(card_request)

        return jsonify(
            {"message": f"Successfully created a card for user ID {test_user_id}.", "card": new_card.model_dump()}
        )

    except Exception as e:
        current_app.logger.error(f"Chek test endpoint failed: {e}")
        current_app.logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@bp.route("/test-ach-payment", methods=["POST"])
def test_ach_payment():
    """An endpoint to test the Chek ACH payment functionality."""
    try:
        chek_service = current_app.chek_service

        # Dummy direct_pay_account_id for testing
        # Replace with an actual active DirectPay account ID from your Chek account
        test_direct_pay_account_id = 90592  # Example DirectPay Account ID
        payment_amount = 5000  # 50.00 USD in cents

        ach_payment_request = ACHPaymentRequest(
            amount=payment_amount,
            type=ACHPaymentType.SAME_DAY_ACH,
            funding_source=ACHFundingSource.WALLET_BALANCE,
        )

        # This will also pre-check if the DirectPay account is Active
        direct_pay_account_response = chek_service.send_ach_payment(
            direct_pay_account_id=test_direct_pay_account_id, request=ach_payment_request
        )

        return jsonify(
            {
                "message": "ACH payment initiated successfully.",
                "direct_pay_account": direct_pay_account_response.model_dump(),
            }
        )

    except Exception as e:
        current_app.logger.error(f"Chek ACH payment test endpoint failed: {e}")
        current_app.logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@bp.route("/test-transfer", methods=["POST"])
def test_transfer():
    """An endpoint to test the Chek balance transfer functionality."""
    try:
        chek_service = current_app.chek_service

        # Dummy user_id and program_id for testing
        # Replace with actual IDs from your Chek account
        test_user_id = 750003  # Example user ID
        test_program_id = "prog_12345"  # Example program ID
        transfer_amount = 1000  # 10.00 USD in cents

        transfer_request = TransferBalanceRequest(
            flow_direction=FlowDirection.PROGRAM_TO_WALLET,
            program_id=test_program_id,
            amount=transfer_amount,
        )

        transfer_response = chek_service.transfer_balance(user_id=test_user_id, request=transfer_request)

        return jsonify(
            {
                "message": "Balance transfer initiated successfully.",
                "transfer_details": transfer_response.model_dump(),
            }
        )

    except Exception as e:
        current_app.logger.error(f"Chek transfer test endpoint failed: {e}")
        current_app.logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500
