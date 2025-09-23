import sentry_sdk
from flask import current_app

from app.models.email_log import EmailLog
from app.utils.email.core import send_email


def resend_email(email_log_id: str) -> bool:
    """
    Resend an email by email_log_id.

    Creates a new email with type "resend" and includes both the original
    email ID and the original context data in the new email's context.

    :param email_log_id: The UUID of the EmailLog to retry
    :return: True if retry was successful, False otherwise
    """
    try:
        email_log = EmailLog.query.filter_by(id=email_log_id).first()

        if not email_log:
            current_app.logger.error(f"EmailLog with id {email_log_id} not found")
            return False

        # Build context that includes original email reference and original context
        resend_context = {
            "original_email_id": str(email_log_id),
            "original_email_type": email_log.email_type,
            "original_sent_at": email_log.created_at.isoformat() if email_log.created_at else None,
            "resend_reason": "manual_resend",
        }

        # Preserve original context data if it exists
        if email_log.context_data:
            resend_context["original_context"] = email_log.context_data

        current_app.logger.info(f"Resending email {email_log_id} as type 'resend'")

        return send_email(
            from_email=email_log.from_email,
            to_emails=email_log.to_emails,
            subject=email_log.subject,
            html_content=email_log.html_content,
            from_name=email_log.from_name,
            email_type="resend",  # Mark as resend type
            context_data=resend_context,  # Include original reference and context
            is_internal=email_log.is_internal,
        )

    except Exception as e:
        current_app.logger.error(f"Failed to resend email {email_log_id}: {e}")

        # Send error to Sentry
        sentry_sdk.capture_exception(
            e,
            extra={
                "email_log_id": email_log_id,
                "email_type": email_log.email_type,
            },
        )

        return False
