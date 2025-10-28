"""
Shared onboarding utilities for families and providers.

This module contains common logic for onboarding users to the CAP system,
including Clerk metadata updates and portal invitation emails.
"""

from typing import Optional

from clerk_backend_api import Clerk
from flask import current_app

from app.auth.decorators import ClerkUserType
from app.supabase.columns import Language


def update_clerk_user_metadata(clerk_user_id: str, user_type: ClerkUserType, entity_id: int):
    """
    Update Clerk user metadata with entity ID and type.

    Args:
        clerk_user_id: Clerk user ID
        user_type: Type of user (FAMILY or PROVIDER)
        entity_id: Family or provider ID

    Raises:
        Exception: If Clerk API call fails
    """
    clerk: Clerk = current_app.clerk_client
    metadata_key = "family_id" if user_type == ClerkUserType.FAMILY else "provider_id"

    clerk.users.update(user_id=clerk_user_id, public_metadata={"types": [user_type.value], metadata_key: entity_id})
    current_app.logger.info(f"Updated Clerk user {clerk_user_id} with {metadata_key} {entity_id}")


def send_portal_invite_email(
    email: str,
    entity_type: str,
    entity_id: int,
    language: Language,
    clerk_user_id: str,
    provider_name: Optional[str] = None,
) -> bool:
    """
    Send portal invitation email to family or provider.

    Args:
        email: Recipient email address
        entity_type: "family" or "provider"
        entity_id: Family or provider ID
        language: Email language preference
        clerk_user_id: Clerk user ID for tracking
        provider_name: Provider name for personalization (providers only)

    Returns:
        True if email sent successfully, False otherwise
    """
    from app.utils.email.config import get_from_email_external
    from app.utils.email.core import send_email
    from app.utils.email.templates import ClerkInvitationTemplate

    fe_domain = current_app.config.get("FRONTEND_DOMAIN")
    portal_url = f"{fe_domain}/auth/sign-in"

    subject = ClerkInvitationTemplate.get_subject(language)

    if entity_type == "family":
        html_content = ClerkInvitationTemplate.get_family_invitation_content(portal_url, language)
    else:
        html_content = ClerkInvitationTemplate.get_provider_invitation_content(portal_url, language, provider_name)

    return send_email(
        from_email=get_from_email_external(),
        to_emails=email,
        subject=subject,
        html_content=html_content,
        email_type=f"{entity_type}_portal_invitation",
        context_data={
            f"{entity_type}_id": entity_id,
            "clerk_user_id": clerk_user_id,
            "language": language.value,
        },
        is_internal=False,
    )
