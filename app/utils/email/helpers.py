"""
Helper utilities for email functionality.
"""

import sys
import traceback
from typing import Optional

import sentry_sdk
from flask import current_app


def capture_sentry_exception(e: Exception, extra_context: dict = None):
    """Helper to capture exceptions in Sentry."""
    sentry_sdk.capture_exception(e, extra=extra_context or {})


def serialize_context_data(context_data: dict) -> dict:
    """Convert non-JSON-serializable objects to strings for JSON storage.
    
    Handles UUIDs, dates, and other objects by converting them to strings.
    Raises ValueError if a value cannot be serialized.
    """
    import json
    from uuid import UUID
    
    if not context_data:
        return {}

    def serialize_value(value):
        # JSON-serializable types: str, int, float, bool, None
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        
        # Handle lists and dicts recursively
        if isinstance(value, list):
            return [serialize_value(item) for item in value]
        if isinstance(value, dict):
            return {k: serialize_value(v) for k, v in value.items()}
            
        # Handle common non-JSON-serializable types
        if isinstance(value, UUID):
            return str(value)
            
        # Try to convert to string as fallback
        try:
            str_value = str(value)
            # Verify it's actually serializable by testing with json
            json.dumps(str_value)
            return str_value
        except (TypeError, ValueError) as e:
            raise ValueError(f"Cannot serialize value of type {type(value).__name__}: {value}") from e

    serializable_context = {}
    for key, value in context_data.items():
        try:
            serializable_context[key] = serialize_value(value)
        except ValueError as e:
            raise ValueError(f"Cannot serialize context_data key '{key}': {e}") from e
            
    return serializable_context


def extract_sendgrid_message_id(response) -> Optional[str]:
    """Extract message ID from SendGrid response headers if available."""
    if hasattr(response, "headers") and "X-Message-Id" in response.headers:
        return response.headers["X-Message-Id"]
    return None


def log_email_error(e: Exception, **context) -> tuple[str, Optional[int]]:
    """
    Log email error with full context and send to Sentry.

    Returns:
        Tuple of (error_message, sendgrid_status_code)
    """
    exc_type, exc_value, _ = sys.exc_info()
    exc_traceback = traceback.format_exc()

    error_context = {
        "exc_traceback": exc_traceback,
        "exc_type": exc_type,
        "exc_value": exc_value,
        **context,
        "e.body": getattr(e, "body", None),
    }

    current_app.logger.error(f"Error sending email: {e}", extra=error_context)
    capture_sentry_exception(e, error_context)

    error_message = str(e)
    sendgrid_status_code = getattr(e, "status_code", None)

    return error_message, sendgrid_status_code
