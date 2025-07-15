from flask import g


def get_current_user():
    """
    Helper function to get current user information.
    Returns None if not authenticated.
    """
    if not hasattr(g, "auth_user_id") or not g.auth_user_id:
        return None

    return {"user_id": g.auth_user_id, "session_id": g.auth_session_id, "request_state": g.auth_request_state}


def is_authenticated():
    """
    Helper function to check if current request is authenticated.
    Returns True if authenticated, False otherwise.
    """
    return hasattr(g, "auth_user_id") and g.auth_user_id is not None
