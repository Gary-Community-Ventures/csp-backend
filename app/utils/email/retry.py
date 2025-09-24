"""
Email retry and resend functionality for handling email operations.
"""

import sentry_sdk
from flask import current_app
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from app.enums.email_type import EmailType
from app.extensions import db
from app.models.email_record import EmailRecord
from app.utils.email.config import add_subject_prefix
from app.utils.email.core import send_email
from app.utils.email.helpers import extract_sendgrid_message_id
from app.utils.email.queries import get_failed_emails


def resend_emails(email_records: list[EmailRecord], resend_successful: bool = False) -> dict:
    """
    Resend or retry a list of emails with flexible filtering.

    :param email_records: List of EmailRecord objects to process
    :param resend_successful: If True, resend successful emails as new records.
                             If False, only retry failed emails (updating same record).
    :return: Dictionary with results
    """
    results = {"total_processed": len(email_records), "successful": 0, "failed": 0, "skipped": 0, "details": []}

    current_app.logger.info(f"Starting {'resend' if resend_successful else 'retry'} for {len(email_records)} emails")

    for email_record in email_records:
        try:
            # Skip non-failed emails when not resending successful ones
            if not resend_successful and not email_record.is_failed:
                results["skipped"] += 1
                results["details"].append(
                    {
                        "email_id": str(email_record.id),
                        "email_type": email_record.email_type,
                        "status": "skipped",
                        "reason": f"Email status is {email_record.status}, not failed",
                    }
                )
                continue

            if resend_successful:
                # Create new email record (resend)
                success = _resend_as_new_email(email_record)
            else:
                # Update existing record (retry)
                success = _retry_existing_email(email_record)

            if success:
                results["successful"] += 1
                results["details"].append(
                    {"email_id": str(email_record.id), "email_type": email_record.email_type, "status": "success"}
                )
            else:
                results["failed"] += 1
                results["details"].append(
                    {"email_id": str(email_record.id), "email_type": email_record.email_type, "status": "failed"}
                )

        except Exception as e:
            results["failed"] += 1
            results["details"].append(
                {
                    "email_id": str(email_record.id),
                    "email_type": getattr(email_record, "email_type", "unknown"),
                    "status": "error",
                    "error": str(e),
                }
            )
            current_app.logger.error(f"Error processing email {email_record.id}: {e}")

    current_app.logger.info(
        f"Batch {'resend' if resend_successful else 'retry'} completed: "
        f"{results['successful']} successful, {results['failed']} failed, {results['skipped']} skipped"
    )

    return results


def _resend_as_new_email(email_record: EmailRecord) -> bool:
    """Create a new email record for resending (used internally)."""
    resend_context = {
        "original_email_id": str(email_record.id),
        "original_email_type": email_record.email_type,
        "original_sent_at": email_record.created_at.isoformat() if email_record.created_at else None,
        "resend_reason": "manual_resend",
    }

    if email_record.context_data:
        resend_context["original_context"] = email_record.context_data

    current_app.logger.info(f"Resending email {email_record.id} as new record")

    return send_email(
        from_email=email_record.from_email,
        to_emails=email_record.to_emails,
        subject=email_record.subject,
        html_content=email_record.html_content,
        email_type=EmailType.RESEND,
        from_name=email_record.from_name,
        context_data=resend_context,
        is_internal=email_record.is_internal,
    )


def _retry_existing_email(email_record: EmailRecord) -> bool:
    """Retry a failed email by updating the existing record (used internally)."""
    try:
        current_app.logger.info(f"Retrying failed email {email_record.id} (attempt #{email_record.attempt_count + 1})")

        message = Mail(
            from_email=(email_record.from_email, email_record.from_name),
            to_emails=email_record.to_emails,
            subject=add_subject_prefix(email_record.subject),
            html_content=email_record.html_content,
        )

        sendgrid_client = SendGridAPIClient(current_app.config.get("SENDGRID_API_KEY"))
        response = sendgrid_client.send(message)

        email_record.mark_as_sent(
            sendgrid_message_id=extract_sendgrid_message_id(response), sendgrid_status_code=response.status_code
        )
        db.session.add(email_record)
        db.session.commit()

        current_app.logger.info(
            f"Successfully retried email {email_record.id} with status code: {response.status_code}"
        )
        return True

    except Exception as e:
        error_message = str(e)
        sendgrid_status_code = getattr(e, "status_code", None)

        email_record.mark_as_failed(error_message=error_message, sendgrid_status_code=sendgrid_status_code)
        db.session.add(email_record)
        db.session.commit()

        current_app.logger.error(f"Failed to retry email {email_record.id}: {e}")

        sentry_sdk.capture_exception(
            e,
            extra={
                "email_record_id": str(email_record.id),
                "attempt_count": email_record.attempt_count,
                "email_type": email_record.email_type,
            },
        )

        return False


# Convenience functions for backward compatibility and common use cases
def retry_failed_email(email_record_id: str) -> bool:
    """Retry a single failed email by ID."""
    email_record = EmailRecord.query.filter_by(id=email_record_id).first()
    if not email_record:
        current_app.logger.error(f"EmailRecord with id {email_record_id} not found")
        return False

    results = resend_emails([email_record], resend_successful=False)
    return results["successful"] > 0


def retry_failed_emails_batch() -> dict:
    """Retry all failed emails in batch."""
    failed_emails = get_failed_emails()
    return resend_emails(failed_emails, resend_successful=False)


def resend_email(email_record_id: str) -> bool:
    """Resend a single email by ID as a new record."""
    email_record = EmailRecord.query.filter_by(id=email_record_id).first()
    if not email_record:
        current_app.logger.error(f"EmailRecord with id {email_record_id} not found")
        return False

    results = resend_emails([email_record], resend_successful=True)
    return results["successful"] > 0
