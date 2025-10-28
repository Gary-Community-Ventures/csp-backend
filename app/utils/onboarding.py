"""
Shared onboarding utilities for families and providers.

This module contains common logic for onboarding users to the CAP system,
including Clerk metadata updates, portal invitation emails, Chek onboarding,
and allocation creation.
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


def onboard_family_to_chek(family_id: int):
    """
    Onboard a family to the Chek payment system.

    This is idempotent - returns existing settings if already created.

    Args:
        family_id: Family ID

    Returns:
        FamilyPaymentSettings instance

    Raises:
        Exception: If Chek onboarding fails
    """
    payment_service = current_app.payment_service
    family_settings = payment_service.onboard_family(family_id)
    current_app.logger.info(f"Onboarded family {family_id} to Chek with user {family_settings.chek_user_id}")
    return family_settings


def onboard_provider_to_chek(provider_id: int):
    """
    Onboard a provider to the Chek payment system.

    This is idempotent - returns existing settings if already created.

    Args:
        provider_id: Provider ID

    Returns:
        ProviderPaymentSettings instance

    Raises:
        Exception: If Chek onboarding fails
    """
    payment_service = current_app.payment_service
    provider_settings = payment_service.onboard_provider(provider_id)
    current_app.logger.info(f"Onboarded provider {provider_id} to Chek with user {provider_settings.chek_user_id}")
    return provider_settings


def create_family_allocations(children: list, family_id: int):
    """
    Create month allocations for payment-enabled children.

    Creates allocations for both current and next month.
    This is idempotent via get_or_create logic.

    Args:
        children: List of child records
        family_id: Family ID for logging

    Returns:
        Tuple of (current_month_result, next_month_result)

    Raises:
        Exception: If allocation creation fails
    """
    from app.services.allocation_service import AllocationService
    from app.supabase.tables import Child
    from app.utils.dates import get_current_month_start, get_next_month_start

    # Filter to payment-enabled children
    payment_enabled_children = [c for c in children if Child.PAYMENT_ENABLED(c)]

    if len(payment_enabled_children) == 0:
        current_app.logger.warning(f"No payment-enabled children found for family {family_id}")
        return None, None

    child_ids = [Child.ID(c) for c in payment_enabled_children]
    allocation_service = AllocationService(current_app)

    current_month_result = allocation_service.create_allocations_for_specific_children(
        child_ids, get_current_month_start()
    )
    next_month_result = allocation_service.create_allocations_for_specific_children(child_ids, get_next_month_start())

    current_app.logger.info(
        f"Created allocations for family {family_id}: "
        f"Current month: {current_month_result.created_count} created, {current_month_result.skipped_count} skipped. "
        f"Next month: {next_month_result.created_count} created, {next_month_result.skipped_count} skipped."
    )

    return current_month_result, next_month_result
