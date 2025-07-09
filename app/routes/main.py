from flask import Blueprint, jsonify, current_app

main_bp = Blueprint("main", __name__)


# Health check endpoint
@main_bp.route("/health")
def health():
    db_status = "disconnected"
    try:
        # Access db from current_app context
        with current_app.extensions["sqlalchemy"].db.engine.connect() as con:
            con.execute(
                current_app.extensions["sqlalchemy"].db.text("SELECT 1")
            )
        db_status = "connected"
    except Exception as e:
        db_status = f"failed: {e}"

    clerk_status = "not initialized"
    if (
        hasattr(current_app, "clerk_client")
        and current_app.clerk_client is not None
    ):
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
@main_bp.route("/")
def index():
    return jsonify(
        {
            "message": "Flask backend API",
            "version": current_app.config.get("APP_VERSION", "unknown"),
        }
    )


# Sentry Test Route (for demonstration purposes, remove in production)
@main_bp.route("/sentry-test")
def sentry_test():
    _ = 1 / 0
    return "This should not be reached if Sentry captures the error."


# Database Sentry Test Route (for demonstration purposes, remove in production)
@main_bp.route("/sentry-db-test")
def sentry_db_test():
    try:
        # Access db from current_app context
        current_app.extensions["sqlalchemy"].db.session.execute(
            current_app.extensions["sqlalchemy"].db.text(
                "SELECT non_existent_column FROM users"
            )
        )
        current_app.extensions["sqlalchemy"].db.session.commit()
    except Exception as e:
        print(f"Database error occurred: {e}")
        return jsonify({"message": f"Database error triggered: {e}"}), 500
    return (
        jsonify(
            {
                "message": (
                    "Database operation attempted ",
                    "(might have failed and been captured by Sentry)"
                )
            }
        ),
        200,
    )
