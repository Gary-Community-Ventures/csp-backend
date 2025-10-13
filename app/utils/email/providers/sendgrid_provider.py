"""
SendGrid email provider implementation.
"""

from http import HTTPStatus
from typing import Union

from flask import current_app
from sendgrid import Personalization, SendGridAPIClient, Substitution, To
from sendgrid.helpers.mail import Mail

from app.utils.email.config import add_subject_prefix
from app.utils.email.helpers import extract_sendgrid_message_id
from app.utils.email.providers import EmailProvider


class SendGridEmailProvider(EmailProvider):
    """SendGrid email provider implementation."""

    def send_email(
        self,
        from_email: str,
        to_emails: Union[str, list[str]],
        subject: str,
        html_content: str,
        from_name: str = "CAP Notifications",
        is_internal: bool = False,
        reply_to: str = None,
    ) -> tuple[bool, str | None, int | None]:
        """Send an email using SendGrid."""
        try:
            message = Mail(
                from_email=(from_email, from_name),
                to_emails=to_emails,
                subject=add_subject_prefix(subject),
                html_content=html_content,
            )

            # Add reply-to if provided
            if reply_to:
                message.reply_to = reply_to

            sendgrid_client = SendGridAPIClient(current_app.config.get("SENDGRID_API_KEY"))
            response = sendgrid_client.send(message)

            sendgrid_message_id = extract_sendgrid_message_id(response)

            current_app.logger.info(f"SendGrid email sent with status code: {response.status_code}")
            return True, sendgrid_message_id, response.status_code

        except Exception as e:
            current_app.logger.error(f"SendGrid error: {str(e)}")
            status_code = getattr(e, "status_code", None) if hasattr(e, "status_code") else None
            return False, None, status_code

    def bulk_send_emails(
        self,
        from_email: str,
        data: list,
        from_name: str = "CAP Notifications",
        is_internal: bool = False,
        reply_to: str = None,
    ) -> tuple[bool, str | None, int | None]:
        """Send bulk emails using SendGrid."""
        try:
            message = Mail(from_email=from_email, to_emails=[], subject="[PLACEHOLDER]", html_content="{body}")

            # Add reply-to if provided
            if reply_to:
                message.reply_to = reply_to

            for message_data in data:
                personalization = Personalization()
                personalization.add_to(To(message_data.email))
                personalization.subject = add_subject_prefix(message_data.subject)
                personalization.add_substitution(Substitution("{body}", message_data.html_content))
                message.add_personalization(personalization)

            sendgrid_client = SendGridAPIClient(current_app.config.get("SENDGRID_API_KEY"))
            response = sendgrid_client.send(message)

            current_app.logger.info(f"SendGrid emails sent with status code: {response.status_code}")

            if response.status_code in [HTTPStatus.OK, HTTPStatus.ACCEPTED]:
                sendgrid_message_id = extract_sendgrid_message_id(response)
                return True, sendgrid_message_id, response.status_code

            return False, None, response.status_code

        except Exception as e:
            current_app.logger.error(f"SendGrid bulk send error: {str(e)}")
            status_code = getattr(e, "status_code", None) if hasattr(e, "status_code") else None
            return False, None, status_code
