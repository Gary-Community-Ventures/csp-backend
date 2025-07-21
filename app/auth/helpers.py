from dataclasses import dataclass
from typing import Optional
from flask import g


@dataclass
class UserData:
    types: list[str]
    family_id: Optional[int] = None
    caregiver_id: Optional[int] = None


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
            caregiver_id=g.auth_user_data.get("caregiver_id", None),
        ),
    )


def is_authenticated():
    """
    Helper function to check if current request is authenticated.
    Returns True if authenticated, False otherwise.
    """
    return hasattr(g, "auth_user_id") and g.auth_user_id is not None
