"""
Email provider factory and interface.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Union


class EmailProviderType(str, Enum):
    """Enum for supported email provider types."""

    SENDGRID = "sendgrid"
    POSTMARK = "postmark"


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


def get_email_provider(email_provider_name: EmailProviderType | str) -> EmailProvider:
    """Factory function to get the appropriate email provider.

    Args:
        email_provider_name: Email provider type (EmailProviderType enum or string)

    Returns:
        EmailProvider: Instance of the requested email provider

    Raises:
        ValueError: If the provider name is not recognized
    """
    from app.utils.email.email_providers.postmark_email_provider import (
        PostmarkEmailProvider,
    )
    from app.utils.email.email_providers.sendgrid_email_provider import (
        SendGridEmailProvider,
    )

    email_providers = {
        EmailProviderType.SENDGRID: SendGridEmailProvider,
        EmailProviderType.POSTMARK: PostmarkEmailProvider,
    }

    # Convert string to enum if needed
    if isinstance(email_provider_name, str):
        try:
            email_provider_name = EmailProviderType(email_provider_name.lower())
        except ValueError:
            available = ", ".join([p.value for p in EmailProviderType])
            raise ValueError(f"Unknown email provider: {email_provider_name}. Available providers: {available}")

    email_provider_class = email_providers.get(email_provider_name)
    if not email_provider_class:
        available = ", ".join([p.value for p in EmailProviderType])
        raise ValueError(f"Unknown email provider: {email_provider_name}. Available providers: {available}")

    return email_provider_class()
