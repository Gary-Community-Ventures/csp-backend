"""
Email configuration helper functions.
"""

from flask import current_app


def add_subject_prefix(subject: str) -> str:
    """Add environment prefix to email subjects for non-production environments."""
    environment = current_app.config.get("FLASK_ENV", "development")
    prefix = ""

    if environment != "production":
        prefix = f"[{environment.upper()}]"

    return f"{prefix} {subject}"


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


def get_internal_email_recipients() -> list[str]:
    """Get internal email recipient list."""
    to_emails = current_app.config.get("INTERNAL_EMAIL_RECIPIENTS", [])

    # Filter out empty strings from the list (in case of trailing commas in env var)
    to_emails = [email.strip() for email in to_emails if email.strip()]

    return to_emails


def get_internal_email_config() -> tuple[str, list[str]]:
    """Get internal email configuration (from address and recipient list)."""
    from_email = get_from_email_internal()
    to_emails = get_internal_email_recipients()
    return from_email, to_emails
