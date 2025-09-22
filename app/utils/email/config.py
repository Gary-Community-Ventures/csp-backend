"""
Email configuration helper functions.
"""

from flask import current_app


def get_from_email_internal() -> str:
    """Get the internal email sender address from configuration."""
    if not current_app.config.get("FROM_EMAIL_INTERNAL"):
        raise ValueError("FROM_EMAIL_INTERNAL is not set in the configuration.")
    return str(current_app.config.get("FROM_EMAIL_INTERNAL"))


def get_from_email_external() -> str:
    """Get the external email sender address from configuration."""
    if not current_app.config.get("FROM_EMAIL_EXTERNAL"):
        raise ValueError("FROM_EMAIL_EXTERNAL is not set in the configuration.")
    return str(current_app.config.get("FROM_EMAIL_EXTERNAL"))


def get_internal_emails() -> tuple[str, list[str]]:
    """Get internal email configuration (from address and recipient list)."""
    # Ensure email addresses are strings
    from_email = get_from_email_internal()
    to_emails = current_app.config.get("INTERNAL_EMAIL_RECIPIENTS", [])

    # Filter out empty strings from the list (in case of trailing commas in env var)
    to_emails = [email.strip() for email in to_emails if email.strip()]

    return from_email, to_emails
