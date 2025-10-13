"""
Core email sending functionality with provider abstraction and logging.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Union

from flask import current_app

from app.extensions import db
from app.models.email_record import EmailRecord, EmailStatus
from app.utils.email.helpers import (
    log_email_error,
    serialize_context_data,
)
from app.utils.email.providers import get_email_provider


@dataclass
class BulkEmailData:
    """Data structure for bulk email sending"""

    email: str
    subject: str
    html_content: str
    context_data: dict = None


def send_email(
    from_email: str,
    to_emails: Union[str, list[str]],
    subject: str,
    html_content: str,
    email_type: str,
    from_name: str = None,
    context_data: dict = None,
    is_internal: bool = False,
) -> bool:
    """
    Send an email using configured email provider with comprehensive logging.

    :param from_email: Sender's email address.
    :param to_emails: Recipient email address(es).
    :param subject: Subject of the email.
    :param html_content: HTML content of the email.
    :param email_type: Type of email for categorization (required).
    :param from_name: Sender's display name. Defaults to "CAP Internal" for internal emails, "CAP Notifications" for external.
    :param context_data: Additional context for logging.
    :param is_internal: Whether this is an internal email.
    :return: True if the email was sent successfully, False otherwise.
    """
    # Default values for optional parameters
    context_data = context_data or {}

    # Set default from_name based on is_internal if not provided
    if from_name is None:
        from_name = "CAP Internal" if is_internal else "CAP Notifications"

    # Normalize to_emails to a list for consistent storage
    if isinstance(to_emails, str):
        to_emails_list = [to_emails]
    else:
        to_emails_list = to_emails

    # Serialize context data for JSON storage
    serializable_context = serialize_context_data(context_data)

    # Get email provider name
    email_provider_name = current_app.config.get("EMAIL_PROVIDER", "sendgrid")

    # Create EmailRecord
    email_record = EmailRecord(
        from_email=from_email,
        to_emails=to_emails_list,
        subject=subject,
        html_content=html_content,
        from_name=from_name,
        email_type=email_type,
        context_data=serializable_context,
        is_internal=is_internal,
        email_provider=email_provider_name,
    )

    try:
        db.session.add(email_record)
        db.session.commit()

        # Get email provider
        email_provider = get_email_provider(email_provider_name)

        # Get reply-to email from config
        reply_to = current_app.config.get("REPLY_TO_EMAIL")

        # Send the email
        success, message_id, status_code = email_provider.send_email(
            from_email=from_email,
            to_emails=to_emails,
            subject=subject,
            html_content=html_content,
            from_name=from_name,
            is_internal=is_internal,
            reply_to=reply_to,
        )

        if success:
            # Mark as successful
            email_record.mark_as_sent(provider_message_id=message_id, provider_status_code=status_code)
            db.session.add(email_record)
            db.session.commit()

            current_app.logger.info(
                f"Email sent successfully via {email_provider_name} with status code: {status_code}"
            )
            return True
        else:
            # Mark as failed
            email_record.mark_as_failed(error_message="Email send failed", provider_status_code=status_code)
            db.session.add(email_record)
            db.session.commit()
            return False

    except Exception as e:
        # Log error and get details
        error_message, provider_status_code = log_email_error(
            e,
            from_email=from_email,
            to_emails=to_emails,
            subject=subject,
            email_type=email_type,
            email_record_id=str(email_record.id),
        )

        # Mark as failed
        email_record.mark_as_failed(error_message=error_message, provider_status_code=provider_status_code)
        db.session.add(email_record)
        db.session.commit()

        return False


def bulk_send_emails(from_email: str, data: list[BulkEmailData], email_type: str, batch_name: str = None):
    """
    Send bulk emails with tracking via BulkEmailBatch model.

    :param from_email: Sender's email address.
    :param data: List of BulkEmailData with recipient information.
    :param email_type: Type of email for categorization (required).
    :param batch_name: Optional name for the batch (for tracking).
    :return: True if successful, False otherwise.
    """
    from app.models.bulk_email_batch import BulkEmailBatch

    # Create batch record for tracking
    if not batch_name:
        batch_name = f"Bulk Email {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"

    batch = BulkEmailBatch(
        batch_name=batch_name,
        batch_type=email_type,
        total_recipients=len(data),
        from_email=from_email,
    )
    db.session.add(batch)
    db.session.flush()

    batch.mark_started()

    # Get email provider name
    email_provider_name = current_app.config.get("EMAIL_PROVIDER", "sendgrid")

    # Create EmailRecord for each email
    email_records = []
    for item in data:
        # Serialize context data for JSON storage
        serializable_context = serialize_context_data(item.context_data or {})

        record = EmailRecord(
            from_email=from_email,
            to_emails=[item.email],
            subject=item.subject,
            html_content=item.html_content,
            status=EmailStatus.PENDING,
            bulk_batch_id=batch.id,
            email_type=email_type,
            context_data=serializable_context,
            email_provider=email_provider_name,
        )
        email_records.append(record)
        db.session.add(record)

    db.session.flush()

    try:
        # Get email provider
        email_provider = get_email_provider(email_provider_name)

        # Get reply-to email from config
        reply_to = current_app.config.get("REPLY_TO_EMAIL")

        # Send bulk emails
        success, message_id, status_code = email_provider.bulk_send_emails(
            from_email=from_email,
            data=data,
            reply_to=reply_to,
        )

        current_app.logger.info(f"Bulk emails sent via {email_provider_name} with status code: {status_code}")

        # Update tracking on success
        if success:
            for record in email_records:
                record.status = EmailStatus.SENT
                record.provider_status_code = status_code
                record.provider_message_id = message_id
            batch.mark_all_sent()
        else:
            # Update tracking on failure
            for record in email_records:
                record.status = EmailStatus.FAILED
                record.error_message = "Bulk send failed"

            batch.mark_all_failed()

        batch.mark_completed()
        db.session.commit()
        return success

    except Exception as e:
        # Log the error
        log_email_error(
            e,
            from_email=from_email,
            batch_id=str(batch.id),
            recipient_count=len(data),
        )

        # Update tracking on failure
        for record in email_records:
            record.status = EmailStatus.FAILED
            record.error_message = str(e)[:500]

        batch.mark_all_failed()
        batch.mark_completed()
        db.session.commit()

        return False
