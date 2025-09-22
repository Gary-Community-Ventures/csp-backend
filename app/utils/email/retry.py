"""
Email retry functionality for handling failed email sends.
"""

import sentry_sdk
from flask import current_app
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from app.models.email_log import EmailLog
from app.utils.email.core import add_subject_prefix
from app.utils.email.queries import get_failed_emails


def retry_failed_email(email_log_id: str) -> bool:
    """
    Retry sending a failed email by email_log_id.

    :param email_log_id: The UUID of the EmailLog to retry
    :return: True if retry was successful, False otherwise
    """
    try:
        email_log = EmailLog.query.filter_by(id=email_log_id).first()

        if not email_log:
            current_app.logger.error(f"EmailLog with id {email_log_id} not found")
            return False

        if not email_log.is_failed:
            current_app.logger.warning(
                f"EmailLog {email_log_id} is not in failed status, current status: {email_log.status}"
            )
            return False

        current_app.logger.info(f"Retrying failed email {email_log_id} (attempt #{email_log.attempt_count + 1})")

        # Attempt to send the email again using the original parameters
        message = Mail(
            from_email=(email_log.from_email, email_log.from_name),
            to_emails=email_log.to_emails,
            subject=add_subject_prefix(email_log.subject),
            html_content=email_log.html_content,
        )

        sendgrid_client = SendGridAPIClient(current_app.config.get("SENDGRID_API_KEY"))
        response = sendgrid_client.send(message)

        # Extract message ID from response headers if available
        sendgrid_message_id = None
        if hasattr(response, "headers") and "X-Message-Id" in response.headers:
            sendgrid_message_id = response.headers["X-Message-Id"]

        # Update the same record as successful
        email_log.mark_as_sent(sendgrid_message_id=sendgrid_message_id, sendgrid_status_code=response.status_code)

        current_app.logger.info(f"Successfully retried email {email_log_id} with status code: {response.status_code}")
        return True

    except Exception as e:
        # Update the same record with the new failure
        error_message = str(e)
        sendgrid_status_code = getattr(e, "status_code", None)

        email_log.mark_as_failed(error_message=error_message, sendgrid_status_code=sendgrid_status_code)

        current_app.logger.error(f"Failed to retry email {email_log_id}: {e}")

        # Send error to Sentry
        sentry_sdk.capture_exception(
            e,
            extra={
                "email_log_id": email_log_id,
                "attempt_count": email_log.attempt_count,
                "email_type": email_log.email_type,
            },
        )

        return False


def retry_failed_emails_batch() -> dict:
    """
    Retry all failed emails in batch.

    :return: Dictionary with retry results
    """
    failed_emails = get_failed_emails()
    results = {"total_failed": len(failed_emails), "retry_successful": 0, "retry_failed": 0, "details": []}

    current_app.logger.info(f"Starting batch retry for {len(failed_emails)} failed emails")

    for email_log in failed_emails:
        try:
            success = retry_failed_email(str(email_log.id))
            if success:
                results["retry_successful"] += 1
                results["details"].append(
                    {"email_id": str(email_log.id), "email_type": email_log.email_type, "status": "success"}
                )
            else:
                results["retry_failed"] += 1
                results["details"].append(
                    {"email_id": str(email_log.id), "email_type": email_log.email_type, "status": "failed"}
                )
        except Exception as e:
            results["retry_failed"] += 1
            results["details"].append(
                {"email_id": str(email_log.id), "email_type": email_log.email_type, "status": "error", "error": str(e)}
            )
            current_app.logger.error(f"Error in batch retry for email {email_log.id}: {e}")

    current_app.logger.info(
        f"Batch retry completed: {results['retry_successful']} successful, {results['retry_failed']} failed"
    )

    return results
