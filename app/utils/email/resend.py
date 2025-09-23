import sentry_sdk
from flask import current_app

from app.models.email_record import EmailRecord
from app.utils.email.core import send_email


def resend_email(email_record_id: str) -> bool:
    """
    Resend an email by email_record_id.

    Creates a new email with type "resend" and includes both the original
    email ID and the original context data in the new email's context.

    :param email_record_id: The UUID of the EmailRecord to retry
    :return: True if retry was successful, False otherwise
    """

    email_record = EmailRecord.query.filter_by(id=email_record_id).first()

    if not email_record:
        current_app.logger.error(f"EmailRecord with id {email_record_id} not found")
        return False

    # Build context that includes original email reference and original context
    resend_context = {
        "original_email_id": str(email_record_id),
        "original_email_type": email_record.email_type,
        "original_sent_at": email_record.created_at.isoformat() if email_record.created_at else None,
        "resend_reason": "manual_resend",
    }

    # Preserve original context data if it exists
    if email_record.context_data:
        resend_context["original_context"] = email_record.context_data

    current_app.logger.info(f"Resending email {email_record_id} as type 'resend'")

    return send_email(
        from_email=email_record.from_email,
        to_emails=email_record.to_emails,
        subject=email_record.subject,
        html_content=email_record.html_content,
        from_name=email_record.from_name,
        email_type="resend",  # Mark as resend type
        context_data=resend_context,  # Include original reference and context
        is_internal=email_record.is_internal,
    )
