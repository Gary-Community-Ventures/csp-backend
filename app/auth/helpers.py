from dataclasses import dataclass
from typing import Optional

from flask import abort, g


@dataclass
class UserData:
    types: list[str]
    family_id: Optional[str] = None
    provider_id: Optional[str] = None


@dataclass
class User:
    user_id: str
    session_id: str
    request_state: any
    user_data: UserData


def get_current_user() -> Optional[User]:
    """
    Helper function to get current user information.
    Returns None if not authenticated.
    """
    if not hasattr(g, "auth_user_id") or not g.auth_user_id:
        return None

    return User(
        user_id=g.auth_user_id,
        session_id=g.auth_session_id,
        request_state=g.auth_request_state,
        user_data=UserData(
            types=g.auth_user_data["types"],
            family_id=g.auth_user_data.get("family_id", None),
            provider_id=g.auth_user_data.get("provider_id", None),
        ),
    )


def get_family_user() -> User:
    user = get_current_user()

    if user is None or user.user_data.family_id is None:
        abort(401)

    return user


def get_provider_user() -> User:
    user = get_current_user()

    if user is None or user.user_data.provider_id is None:
        abort(401)

    return user


def is_authenticated():
    """
    Helper function to check if current request is authenticated.
    Returns True if authenticated, False otherwise.
    """
    return hasattr(g, "auth_user_id") and g.auth_user_id is not None
