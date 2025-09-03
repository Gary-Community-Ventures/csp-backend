import sentry_sdk
from flask import abort, current_app

from app.constants import UNKNOWN
from app.supabase.columns import Column


def cols(*args: Column):
    if len(args) == 0:
        return "*"

    return ", ".join([str(a) for a in args])


def unwrap_or_abort(response):
    """
    Check for errors in Supabase response and return data if successful.
    Aborts with 502 if there's an error.

    Args:
        response: The response object from a Supabase query

    Returns:
        The data from the response

    Raises:
        HTTPException: 502 Bad Gateway if Supabase returns an error
    """
    if hasattr(response, "error") and response.error:
        error_msg = f"Supabase query error: {response.error}"
        current_app.logger.error(error_msg)
        sentry_sdk.capture_message(
            error_msg, level="error", extras={"error": response.error, "response": str(response) if response else None}
        )
        abort(502, description="Database query failed")

    if not hasattr(response, "data"):
        error_msg = "Supabase response missing data attribute"
        current_app.logger.error(error_msg)
        sentry_sdk.capture_message(error_msg, level="error", extras={"response": str(response) if response else None})
        abort(502, description="Database query failed")

    return response.data


FIRST_NAME_COLUMN = Column("first_name")
LAST_NAME_COLUMN = Column("last_name")


def format_name(data: dict) -> str:
    first_name = FIRST_NAME_COLUMN(data)
    last_name = LAST_NAME_COLUMN(data)

    if first_name is None or last_name is None:
        return UNKNOWN

    return f"{first_name} {last_name}"
