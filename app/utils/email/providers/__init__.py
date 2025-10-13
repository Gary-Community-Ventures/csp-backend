"""
Email provider factory and interface.
"""

from abc import ABC, abstractmethod
from typing import Union


class EmailProvider(ABC):
    """Abstract base class for email providers."""

    @abstractmethod
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
        """
        Send an email.

        Args:
            from_email: Sender's email address
            to_emails: Recipient email address(es)
            subject: Email subject
            html_content: HTML body content
            from_name: Sender's display name
            is_internal: Whether this is an internal email
            reply_to: Reply-to email address

        Returns:
            tuple: (success: bool, message_id: str | None, status_code: int | None)
        """
        pass

    @abstractmethod
    def bulk_send_emails(
        self,
        from_email: str,
        data: list,
        from_name: str = "CAP Colorado",
        is_internal: bool = False,
        reply_to: str = None,
    ) -> tuple[bool, str | None, int | None]:
        """
        Send bulk emails.

        Args:
            from_email: Sender's email address
            data: List of email data
            from_name: Sender's display name
            is_internal: Whether these are internal emails
            reply_to: Reply-to email address

        Returns:
            tuple: (success: bool, message_id: str | None, status_code: int | None)
        """
        pass


def get_email_provider(email_provider_name: str) -> EmailProvider:
    """Factory function to get the appropriate email provider."""
    from app.utils.email.providers.postmark_provider import PostmarkEmailProvider
    from app.utils.email.providers.sendgrid_provider import SendGridEmailProvider

    email_providers = {
        "sendgrid": SendGridEmailProvider,
        "postmark": PostmarkEmailProvider,
    }

    email_provider_class = email_providers.get(email_provider_name.lower())
    if not email_provider_class:
        raise ValueError(
            f"Unknown email provider: {email_provider_name}. Available providers: {', '.join(email_providers.keys())}"
        )

    return email_provider_class()
