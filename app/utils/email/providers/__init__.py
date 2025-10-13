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
        from_name: str = "CAP Notifications",
        is_internal: bool = False,
    ) -> tuple[bool, str | None, int | None]:
        """
        Send an email.

        Returns:
            tuple: (success: bool, message_id: str | None, status_code: int | None)
        """
        pass

    @abstractmethod
    def bulk_send_emails(
        self,
        from_email: str,
        data: list,
        from_name: str = "CAP Notifications",
        is_internal: bool = False,
    ) -> tuple[bool, str | None, int | None]:
        """
        Send bulk emails.

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
