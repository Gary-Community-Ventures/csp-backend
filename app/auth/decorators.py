import hmac
from enum import Enum
from functools import wraps

import httpx
from clerk_backend_api import Clerk
from clerk_backend_api.security.types import AuthenticateRequestOptions
from flask import abort, current_app, g, request


class ClerkUserType(Enum):
    ADMIN = "admin"
    FAMILY = "family"
    PROVIDER = "provider"
    NONE = None


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
        "AUTH_AUTHORIZED_PARTIES",
    )


def _authenticate_request(user_type: ClerkUserType, allow_cookies: bool = False):
    """
    Core authentication logic
    Returns: request_state object if authenticated
    Raises: AuthenticationError if not authenticated
    """
    if not allow_cookies:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise AuthenticationError("Bearer token required")

    clerk_client: Clerk = current_app.clerk_client
    if not clerk_client:
        raise AuthenticationError("Authentication service not initialized", 500)

    httpx_request = _create_httpx_request()

    try:
        request_state = clerk_client.authenticate_request(
            httpx_request,
            AuthenticateRequestOptions(authorized_parties=_get_authorized_parties(), clock_skew_in_ms=1000 * 30),
        )

        if not request_state.is_signed_in:
            current_app.logger.warning(f"User is not signed in: {request_state.message}")
            raise AuthenticationError("User is not signed in")

        if user_type == ClerkUserType.NONE:
            return request_state

        if user_type.value not in request_state.payload.get("data").get("types", []):
            raise AuthenticationError("User is not authorized")

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


def _authenticate_api_key():
    """
    Authenticate API key from request headers
    Returns: True if authenticated
    Raises: AuthenticationError if not authenticated
    """
    # Get API key from multiple possible headers
    api_key = request.headers.get("X-API-Key") or request.headers.get("Authorization")

    if not api_key:
        raise AuthenticationError("API key required", 401)

    # Handle Bearer token format
    if api_key.startswith("Bearer "):
        api_key = api_key[7:]  # Remove 'Bearer ' prefix

    # Get expected API key from config
    expected_api_key = current_app.config.get("API_KEY")

    if not expected_api_key:
        current_app.logger.error("API_KEY not configured")
        raise AuthenticationError("API authentication not configured", 500)

    # Use constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(api_key.encode("utf-8"), expected_api_key.encode("utf-8")):
        current_app.logger.warning(f"Invalid API key attempt from {request.remote_addr}")
        raise AuthenticationError("Invalid API key", 401)

    return True


def _set_user_context(request_state):
    """Set user context in Flask g object"""
    g.auth_request_state = request_state
    g.auth_user_id = request_state.payload.get("sub", None)
    g.auth_session_id = request_state.payload.get("sid", None)
    g.auth_issued_at = request_state.payload.get("iat", None)
    g.auth_expires_at = request_state.payload.get("exp", None)
    g.auth_issuer = request_state.payload.get("iss", None)
    g.auth_user_data = request_state.payload.get("data", None)


def _clear_user_context():
    """Clear user context from Flask g object"""
    g.auth_request_state = None
    g.auth_user_id = None
    g.auth_session_id = None
    g.auth_issued_at = None
    g.auth_expires_at = None
    g.auth_issuer = None
    g.auth_user_data = None


def auth_required(user_type: ClerkUserType):
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
    - g.auth_user_data: Custom user data from token or None
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                request_state = _authenticate_request(user_type=user_type)
                _set_user_context(request_state)

                return f(*args, **kwargs)

            except AuthenticationError as e:
                abort(e.status_code, description=e.args[0])

        return decorated_function

    return decorator


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
            request_state = _authenticate_request(ClerkUserType.NONE)
            _set_user_context(request_state)

        except AuthenticationError as e:
            # For optional auth, we don't abort on errors
            current_app.logger.debug(f"Optional authentication failed: {e}")
            _clear_user_context()

        return f(*args, **kwargs)

    return decorated_function


def api_key_required(f):
    """
    Decorator that requires API key authentication.
    Aborts with 401 if API key is not valid.

    Accepts API key in:
    - X-API-Key header
    - Authorization header (with or without 'Bearer ' prefix)
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            _authenticate_api_key()

            return f(*args, **kwargs)

        except AuthenticationError as e:
            abort(e.status_code, description=e.args[0])

    return decorated_function
