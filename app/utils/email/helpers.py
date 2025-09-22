"""
Helper utilities for email functionality.
"""

import sys
import traceback
from typing import Any, Optional

import sentry_sdk
from flask import current_app


def capture_sentry_exception(e: Exception, extra_context: dict = None):
    """Helper to capture exceptions in Sentry."""
    sentry_sdk.capture_exception(e, extra=extra_context or {})


def serialize_context_data(context_data: dict) -> dict:
    """Convert UUIDs and other non-serializable objects to strings for JSON storage."""
    if not context_data:
        return {}

    serializable_context = {}
    for key, value in context_data.items():
        if hasattr(value, "__class__") and value.__class__.__name__ == "UUID":
            serializable_context[key] = str(value)
        elif isinstance(value, list):
            # Handle lists that might contain UUIDs
            serializable_context[key] = [
                str(v) if hasattr(v, "__class__") and v.__class__.__name__ == "UUID" else v for v in value
            ]
        else:
            serializable_context[key] = value
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
