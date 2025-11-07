from datetime import datetime, timezone
from typing import Optional

import sentry_sdk
from flask import abort, current_app

from app.constants import UNKNOWN
from app.supabase.columns import Column


def cols(*args: Column):
    if len(args) == 0:
        return "*"

    return ", ".join([str(a) for a in args])


class UnwrapError(Exception):
    pass


def unwrap_or_error(response):
    """
    Check for errors in Supabase response and return data if successful.
    Raises an error if there's an error.

    Args:
        response: The response object from a Supabase query
    Returns:
        The data from the response
    """
    if hasattr(response, "error") and response.error:
        error_msg = f"Supabase query error: {response.error}"
        current_app.logger.error(error_msg)
        sentry_sdk.capture_message(
            error_msg, level="error", extras={"error": response.error, "response": str(response) if response else None}
        )
        raise UnwrapError(error_msg)

    if not hasattr(response, "data"):
        error_msg = f"Supabase response missing data attribute: {response}"
        current_app.logger.error(error_msg)
        sentry_sdk.capture_message(error_msg, level="error", extras={"response": str(response) if response else None})
        raise UnwrapError(error_msg)

    return response.data


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
    try:
        return unwrap_or_error(response)
    except UnwrapError:
        abort(502, description="Database query failed")


FIRST_NAME_COLUMN = Column("first_name")
LAST_NAME_COLUMN = Column("last_name")


def format_name(data: Optional[dict]) -> str:
    if data is None:
        return UNKNOWN

    first_name = FIRST_NAME_COLUMN(data)
    last_name = LAST_NAME_COLUMN(data)

    if first_name is None or last_name is None:
        return UNKNOWN

    return f"{first_name} {last_name}"


def set_timestamp_column_if_null(table_class, id_column_value: str, timestamp_column, timestamp_value: str = None):
    """
    Helper to set a timestamp column if it's currently null.

    This is useful for tracking "first time" events like when a provider first invites
    a family, or when payment is first configured.

    Args:
        table_class: The Table class (e.g., Provider, Family)
        id_column_value: The ID value to match
        timestamp_column: The Column object to update (e.g., Provider.FAMILY_INVITED_AT)
        timestamp_value: Optional ISO timestamp string. Defaults to current UTC time.

    Example:
        set_timestamp_column_if_null(Provider, provider_id, Provider.FAMILY_INVITED_AT)
    """
    if timestamp_value is None:
        timestamp_value = datetime.now(timezone.utc).isoformat()

    table_class.query().update({timestamp_column: timestamp_value}).eq(table_class.ID, id_column_value).is_(
        timestamp_column, "null"
    ).execute()
