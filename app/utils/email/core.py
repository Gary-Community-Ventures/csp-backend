"""
Core email sending functionality with SendGrid integration and logging.
"""

import sys
import traceback
from dataclasses import dataclass
from datetime import datetime
from typing import Union

import sentry_sdk
from flask import current_app
from sendgrid import Personalization, SendGridAPIClient, Substitution, To
from sendgrid.helpers.mail import Mail

from app.extensions import db
from app.models.email_log import EmailLog, EmailStatus


def capture_sentry_exception(e: Exception, extra_context: dict = None):
    """Helper to capture exceptions in Sentry"""
    sentry_sdk.capture_exception(e, extra=extra_context or {})


def add_subject_prefix(subject: str):
    """Add environment prefix to email subjects for non-production environments"""
    environment = current_app.config.get("FLASK_ENV", "development")
    prefix = ""

    if environment != "production":
        prefix = f"[{environment.upper()}]"

    return f"{prefix} {subject}"


@dataclass
class BulkEmailData:
    """Data structure for bulk email sending"""

    email: str
    subject: str
    html_content: str


def send_email_with_logging(
    from_email: str,
    to_emails: Union[str, list[str]],
    subject: str,
    html_content: str,
    from_name: str = "CAP Support",
    email_type: str = None,
    context_data: dict = None,
    is_internal: bool = False,
) -> bool:
    """
    Send an email using SendGrid with comprehensive logging.

    :param from_email: Sender's email address.
    :param to_emails: Recipient email address(es).
    :param subject: Subject of the email.
    :param html_content: HTML content of the email.
    :param from_name: Sender's display name.
    :param email_type: Type of email for categorization.
    :param context_data: Additional context for logging.
    :param is_internal: Whether this is an internal email.
    :return: True if the email was sent successfully, False otherwise.
    """
    # Normalize to_emails to a list for consistent storage
    if isinstance(to_emails, str):
        to_emails_list = [to_emails]
    else:
        to_emails_list = to_emails

    # Convert UUIDs and other non-serializable objects in context_data to strings
    if context_data:
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
    else:
        serializable_context = {}

    # Create EmailLog record
    email_log = EmailLog(
        from_email=from_email,
        to_emails=to_emails_list,
        subject=subject,
        html_content=html_content,
        from_name=from_name,
        email_type=email_type,
        context_data=serializable_context,
        is_internal=is_internal,
    )

    try:
        db.session.add(email_log)
        db.session.commit()

        # Send the email
        message = Mail(
            from_email=(from_email, from_name),
            to_emails=to_emails,
            subject=add_subject_prefix(subject),
            html_content=html_content,
        )

        sendgrid_client = SendGridAPIClient(current_app.config.get("SENDGRID_API_KEY"))
        response = sendgrid_client.send(message)

        # Extract message ID from response headers if available
        sendgrid_message_id = None
        if hasattr(response, "headers") and "X-Message-Id" in response.headers:
            sendgrid_message_id = response.headers["X-Message-Id"]

        # Mark as successful
        email_log.mark_as_sent(sendgrid_message_id=sendgrid_message_id, sendgrid_status_code=response.status_code)

        current_app.logger.info(f"SendGrid email sent with status code: {response.status_code}")
        return True

    except Exception as e:
        # Mark as failed and capture error details
        error_message = str(e)
        sendgrid_status_code = getattr(e, "status_code", None)

        email_log.mark_as_failed(error_message=error_message, sendgrid_status_code=sendgrid_status_code)

        # Log detailed error information
        exc_type, exc_value, _ = sys.exc_info()
        exc_traceback = traceback.format_exc()

        error_context = {
            "exc_traceback": exc_traceback,
            "exc_type": exc_type,
            "exc_value": exc_value,
            "from_email": from_email,
            "to_emails": to_emails,
            "subject": subject,
            "email_type": email_type,
            "email_log_id": str(email_log.id),
            "e.body": getattr(e, "body", None),
        }

        current_app.logger.error(f"Error sending email: {e}", extra=error_context)

        # Send error to Sentry for monitoring
        capture_sentry_exception(e, error_context)

        return False


def send_email(
    from_email: str,
    to_emails: Union[str, list[str]],
    subject: str,
    html_content: str,
    from_name: str = "CAP Support",
    email_type: str = None,
    context_data: dict = None,
    is_internal: bool = False,
) -> bool:
    """
    Send an email using SendGrid with comprehensive logging.
    """
    return send_email_with_logging(
        from_email=from_email,
        to_emails=to_emails,
        subject=subject,
        html_content=html_content,
        from_name=from_name,
        email_type=email_type or "legacy",
        context_data=context_data or {},
        is_internal=is_internal,
    )


def bulk_send_emails(from_email: str, data: list[BulkEmailData], batch_name: str = None):
    """
    Send bulk emails with tracking via BulkEmailBatch model.

    :param from_email: Sender's email address.
    :param data: List of BulkEmailData with recipient information.
    :param batch_name: Optional name for the batch (for tracking).
    :return: True if successful, False otherwise.
    """
    from app.models.bulk_email_batch import BatchStatus, BulkEmailBatch

    # Create batch record for tracking
    if not batch_name:
        batch_name = f"Bulk Email {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"

    batch = BulkEmailBatch(
        batch_name=batch_name,
        batch_type="bulk_send",
        total_recipients=len(data),
        from_email=from_email,
        initiated_by="bulk_send_emails",
    )
    db.session.add(batch)
    db.session.flush()

    batch.mark_started()

    # Create EmailLog records for each email
    email_logs = []
    for item in data:
        log = EmailLog(
            from_email=from_email,
            to_emails=[item.email],
            subject=item.subject,
            html_content=item.html_content,
            status=EmailStatus.PENDING,
            bulk_batch_id=batch.id,
        )
        email_logs.append(log)
        db.session.add(log)

    db.session.flush()

    try:
        message = Mail(from_email=from_email, to_emails=[], subject="[PLACEHOLDER]", html_content="{body}")

        for message_data in data:
            personalization = Personalization()
            personalization.add_to(To(message_data.email))
            personalization.subject = add_subject_prefix(message_data.subject)
            personalization.add_substitution(Substitution("{body}", message_data.html_content))

            message.add_personalization(personalization)

        sendgrid_client = SendGridAPIClient(current_app.config.get("SENDGRID_API_KEY"))
        response = sendgrid_client.send(message)
        current_app.logger.info(f"SendGrid emails sent with status code: {response.status_code}")

        # Update tracking on success
        if response.status_code in [200, 202]:
            for log in email_logs:
                log.status = EmailStatus.SENT
                log.sendgrid_status_code = response.status_code
            batch.successful_sends = len(email_logs)
            batch.failed_sends = 0

        batch.mark_completed()
        db.session.commit()
        return True
    except Exception as e:
        exc_type, exc_value, _ = sys.exc_info()
        exc_traceback = traceback.format_exc()
        current_app.logger.error(
            f"Error sending email: {e}",
            extra={
                "exc_traceback": exc_traceback,
                "exc_type": exc_type,
                "exc_value": exc_value,
                "from_email": from_email,
                "data": data,
                "e.body": getattr(e, "body", None),
            },
        )
        current_app.logger.error(exc_traceback)

        # Update tracking on failure
        for log in email_logs:
            log.status = EmailStatus.FAILED
            log.error_message = str(e)[:500]
        batch.failed_sends = len(email_logs)
        batch.successful_sends = 0
        batch.status = BatchStatus.FAILED
        batch.mark_completed()
        db.session.commit()

        return False
