from flask import Blueprint, jsonify, current_app
from app.jobs import get_job_status, retry_failed_job, get_queue_info

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
def sentry_test():
    _ = 1 / 0
    return "This should not be reached if Sentry captures the error."


# Database Sentry Test Route (for demonstration purposes, remove in production)
@bp.route("/sentry-db-test")
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

@bp.route('/jobs/<job_id>/status', methods=['GET'])
def job_status(job_id):
    status = get_job_status(job_id)
    return jsonify(status)

@bp.route('/jobs/<job_id>/retry', methods=['POST'])
def retry_job(job_id):
    result = retry_failed_job(job_id)
    return jsonify(result)

@bp.route('/jobs/queue-info', methods=['GET'])
def queue_info():
    info = get_queue_info()
    return jsonify(info)

@bp.route('/example-job', methods=['POST'])
def example_job():
    # Call the job function here
    return jsonify({"message": "Example job enqueued"}), 202
