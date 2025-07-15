import httpx
from flask import request, abort, g, current_app
from functools import wraps
from clerk_backend_api.security.types import AuthenticateRequestOptions


class AuthenticationError(Exception):
    """Custom exception for authentication errors"""

    def __init__(self, message, status_code=401):
        super().__init__(message)
        self.status_code = status_code


def _create_httpx_request():
    """Helper function to convert Flask request to httpx.Request"""
    return httpx.Request(
        method=request.method, url=str(request.url), headers=dict(request.headers), content=request.get_data()
    )


def _get_authorized_parties():
    """Get authorized parties from config or use defaults"""
    return current_app.config.get(
        "AUTH_AUTHORIZED_PARTIES", ["http://localhost:3000", "http://localhost:5173", "https://yourdomain.com"]
    )


def _authenticate_request():
    """
    Core authentication logic
    Returns: request_state object if authenticated
    Raises: AuthenticationError if not authenticated
    """
    clerk_client = current_app.clerk_client
    if not clerk_client:
        raise AuthenticationError("Authentication service not initialized", 500)

    httpx_request = _create_httpx_request()

    try:
        request_state = clerk_client.authenticate_request(
            httpx_request, AuthenticateRequestOptions(authorized_parties=_get_authorized_parties())
        )

        if not request_state.is_signed_in:
            raise AuthenticationError("User is not signed in")

        return request_state

    except AuthenticationError as e:
        # Handle known authentication errors
        current_app.logger.warning(f"Authentication error: {e}")
        raise e

    except ValueError as e:
        # Handle token parsing/JSON errors
        current_app.logger.warning(f"Token parsing error: {e}")
        raise AuthenticationError("Invalid token format")

    except Exception as e:
        # Handle unexpected errors
        current_app.logger.error(f"Unexpected authentication error: {e}")

        # Check if it's likely an authentication-related error
        error_str = str(e).lower()
        if any(keyword in error_str for keyword in ["401", "unauthorized", "authentication", "token"]):
            raise AuthenticationError("Authentication failed")
        else:
            raise AuthenticationError("Authentication service error", 500)


def _set_user_context(request_state):
    """Set user context in Flask g object"""
    g.auth_request_state = request_state
    g.auth_user_id = request_state.payload.get("sub", None)
    g.auth_session_id = request_state.payload.get("sid", None)
    g.auth_issued_at = request_state.payload.get("iat", None)
    g.auth_expires_at = request_state.payload.get("exp", None)
    g.auth_issuer = request_state.payload.get("iss", None)


def _clear_user_context():
    """Clear user context from Flask g object"""
    g.auth_request_state = None
    g.auth_user_id = None
    g.auth_session_id = None
    g.auth_issued_at = None
    g.auth_expires_at = None
    g.auth_issuer = None


def auth_required(f):
    """
    Decorator that requires authentication.
    Aborts with 401 if user is not authenticated.

    Sets the following in Flask g:
    - g.auth_request_state: Full request state object
    - g.auth_user_id: User ID from token
    - g.auth_session_id: Session ID from token
    - g.auth_issued_at: Issued at timestamp or None
    - g.auth_expires_at: Expiration timestamp or None
    - g.auth_issuer: Issuer URL or None
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            request_state = _authenticate_request()
            _set_user_context(request_state)

            return f(*args, **kwargs)

        except AuthenticationError as e:
            abort(e.status_code, description=e.args[0])

    return decorated_function


def auth_optional(f):
    """
    Decorator that optionally authenticates users.
    Sets user context if authenticated, but doesn't require it.

    Sets the following in Flask g (None if not authenticated):
    - g.auth_request_state: Full request state object or None
    - g.auth_user_id: User ID from token or None
    - g.auth_session_id: Session ID from token or None
    - g.auth_issued_at: Issued at timestamp or None
    - g.auth_expires_at: Expiration timestamp or None
    - g.auth_issuer: Issuer URL or None
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            request_state = _authenticate_request()
            _set_user_context(request_state)

        except AuthenticationError as e:
            # For optional auth, we don't abort on errors
            current_app.logger.debug(f"Optional authentication failed: {e}")
            _clear_user_context()

        return f(*args, **kwargs)

    return decorated_function
