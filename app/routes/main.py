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
