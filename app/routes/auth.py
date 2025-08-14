from flask import Blueprint, g, jsonify

from ..auth.decorators import ClerkUserType, auth_optional, auth_required
from ..auth.helpers import get_current_user, is_authenticated

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/protected")
@auth_required(ClerkUserType.FAMILY)
def protected_route():
    """Protected route requiring authentication"""
    return jsonify(
        {
            "message": f"Welcome, user {g.auth_user_id}!",
            "user_id": g.auth_user_id,
            "session_id": g.auth_session_id,
        }
    )


@bp.route("/user")
@auth_optional
def user_info():
    """Route that works with or without authentication"""
    if is_authenticated():
        # You can access the full request state to get user details
        user_data = g.auth_request_state.payload
        return jsonify(
            {
                "authenticated": True,
                "user_id": g.auth_user_id,
                "session_id": g.auth_session_id,
                "token_data": user_data,  # This contains the full JWT payload
            }
        )
    else:
        return jsonify({"authenticated": False})


@bp.route("/me")
@auth_required(ClerkUserType.FAMILY)
def get_user_details():
    """Get detailed user information from the token payload"""
    # Access the full token payload
    token_payload = g.auth_request_state.payload

    return jsonify(
        {
            "token_payload": token_payload,
            "user_id": g.auth_user_id,
            "session_id": g.auth_session_id,
            "issued_at": g.auth_issued_at,
            "expires_at": g.auth_expires_at,
            "issuer": g.auth_issuer,
        }
    )


@bp.route("/status")
@auth_optional
def auth_status():
    """Check authentication status using helper function"""
    user = get_current_user()

    if user:
        return jsonify(
            {"authenticated": True, "user_id": user.user_id, "session_id": user.session_id, "user_data": user.user_data}
        )
    else:
        return jsonify({"authenticated": False})
