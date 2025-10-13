"""
Postmark email provider implementation.
"""

from http import HTTPStatus
from typing import Union

from flask import current_app
from postmarker.core import PostmarkClient

from app.utils.email.config import add_subject_prefix
from app.utils.email.providers import EmailProvider


class PostmarkEmailProvider(EmailProvider):
    """Postmark email provider implementation."""

    def send_email(
        self,
        from_email: str,
        to_emails: Union[str, list[str]],
        subject: str,
        html_content: str,
        from_name: str = "CAP Colorado",
        is_internal: bool = False,
        reply_to: str = None,
    ) -> tuple[bool, str | None, int | None]:
        """Send an email using Postmark."""
        try:
            postmark_client = PostmarkClient(server_token=current_app.config.get("POSTMARK_API_KEY"))

            # Normalize to_emails to a comma-separated string
            if isinstance(to_emails, list):
                to_emails_str = ",".join(to_emails)
            else:
                to_emails_str = to_emails

            # Get the appropriate message stream based on is_internal
            if is_internal:
                message_stream = current_app.config.get("POSTMARK_STREAM_INTERNAL", "internal")
            else:
                message_stream = current_app.config.get("POSTMARK_STREAM_EXTERNAL", "notifications")

            # Build email parameters
            email_params = {
                "From": f"{from_name} <{from_email}>",
                "To": to_emails_str,
                "Subject": add_subject_prefix(subject),
                "HtmlBody": html_content,
                "MessageStream": message_stream,
            }

            # Add reply-to if provided
            if reply_to:
                email_params["ReplyTo"] = reply_to

            response = postmark_client.emails.send(**email_params)

            message_id = response.get("MessageID")
            current_app.logger.info(f"Postmark email sent successfully. Message ID: {message_id}")
            return True, message_id, HTTPStatus.OK

        except Exception as e:
            current_app.logger.error(f"Postmark error: {str(e)}")
            status_code = getattr(e, "status_code", None) if hasattr(e, "status_code") else None
            return False, None, status_code

    def bulk_send_emails(
        self,
        from_email: str,
        data: list,
        from_name: str = "CAP Colorado",
        is_internal: bool = False,
        reply_to: str = None,
    ) -> tuple[bool, str | None, int | None]:
        """Send bulk emails using Postmark."""
        try:
            postmark_client = PostmarkClient(server_token=current_app.config.get("POSTMARK_API_KEY"))

            # Get the appropriate message stream based on is_internal
            if is_internal:
                message_stream = current_app.config.get("POSTMARK_STREAM_INTERNAL", "internal")
            else:
                message_stream = current_app.config.get("POSTMARK_STREAM_EXTERNAL", "notifications")

            # Build batch of emails
            emails = []
            for message_data in data:
                email_params = {
                    "From": f"{from_name} <{from_email}>",
                    "To": message_data.email,
                    "Subject": add_subject_prefix(message_data.subject),
                    "HtmlBody": message_data.html_content,
                    "MessageStream": message_stream,
                }

                # Add reply-to if provided
                if reply_to:
                    email_params["ReplyTo"] = reply_to

                emails.append(email_params)

            # Send batch
            response = postmark_client.emails.send_batch(*emails)

            current_app.logger.info(f"Postmark batch emails sent successfully. Count: {len(emails)}")

            # Extract first message ID if available
            message_id = None
            if response and len(response) > 0:
                message_id = response[0].get("MessageID")

            return True, message_id, HTTPStatus.OK

        except Exception as e:
            current_app.logger.error(f"Postmark bulk send error: {str(e)}")
            status_code = getattr(e, "status_code", None) if hasattr(e, "status_code") else None
            return False, None, status_code
