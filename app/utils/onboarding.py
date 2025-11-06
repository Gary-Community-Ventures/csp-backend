"""
Shared onboarding utilities for families and providers.

This module contains common logic for onboarding users to the CAP system,
including Clerk metadata updates, portal invitation emails, Chek onboarding,
and allocation creation.
"""

from typing import Optional

from clerk_backend_api import Clerk
from flask import abort, current_app

from app.auth.decorators import ClerkUserType
from app.constants import MAX_CHILDREN_PER_PROVIDER
from app.extensions import db
from app.models.family_invitation import FamilyInvitation
from app.models.provider_invitation import ProviderInvitation
from app.services.allocation_service import AllocationService
from app.supabase.columns import Language
from app.supabase.helpers import cols, unwrap_or_abort
from app.supabase.tables import Child, Family, Provider, ProviderChildMapping
from app.utils.date_utils import get_current_month_start, get_next_month_start
from app.utils.email.config import get_from_email_external
from app.utils.email.core import send_email
from app.utils.email.templates import ClerkInvitationTemplate


def update_clerk_user_metadata(clerk_user_id: str, user_type: ClerkUserType, entity_id: str):
    """
    Update Clerk user metadata with entity ID and type.

    Appends to 'types' array and adds the entity ID key (family_id or provider_id)
    in the public_metadata, preserving existing metadata. This allows a user to be
    both a family and a provider.

    Args:
        clerk_user_id: Clerk user ID
        user_type: Type of user (FAMILY or PROVIDER)
        entity_id: Family or provider ID (as string)

    Raises:
        Exception: If Clerk API call fails
    """
    clerk: Clerk = current_app.clerk_client
    metadata_key = "family_id" if user_type == ClerkUserType.FAMILY else "provider_id"

    # Fetch existing metadata
    user = clerk.users.get(user_id=clerk_user_id)
    existing_metadata = user.public_metadata or {}

    # Get existing types array and append new type if not already present
    existing_types = existing_metadata.get("types", [])
    if user_type.value not in existing_types:
        existing_types.append(user_type.value)

    # Build updated metadata, merging with existing
    updated_metadata = {
        **existing_metadata,
        "types": existing_types,
        metadata_key: entity_id,
    }

    clerk.users.update(user_id=clerk_user_id, public_metadata=updated_metadata)
    current_app.logger.info(
        f"Updated Clerk user {clerk_user_id} with types={existing_types} and {metadata_key}={entity_id}"
    )


def send_portal_invite_email(
    email: str,
    entity_type: ClerkUserType,
    entity_id: int,
    language: Language,
    clerk_user_id: str,
    provider_name: Optional[str] = None,
) -> bool:
    """
    Send portal invitation email to family or provider.

    Args:
        email: Recipient email address
        entity_type: ClerkUserType.FAMILY or ClerkUserType.PROVIDER
        entity_id: Family or provider ID
        language: Email language preference
        clerk_user_id: Clerk user ID for tracking
        provider_name: Provider name for personalization (providers only)

    Returns:
        True if email sent successfully, False otherwise
    """
    fe_domain = current_app.config.get("FRONTEND_DOMAIN")
    portal_url = f"{fe_domain}/auth/sign-in"

    subject = ClerkInvitationTemplate.get_subject(language)

    if entity_type == ClerkUserType.FAMILY:
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

    Raises:
        werkzeug.exceptions.BadRequest: If no allocations were created for payment-enabled children
    """

    # Filter to payment-enabled children
    payment_enabled_children = [c for c in children if Child.PAYMENT_ENABLED(c)]

    if len(payment_enabled_children) == 0:
        current_app.logger.warning(f"No payment-enabled children found for family {family_id}")
        return

    child_ids = [Child.ID(c) for c in payment_enabled_children]
    allocation_service = AllocationService(current_app)

    current_month_result = allocation_service.create_allocations_for_specific_children(
        child_ids, get_current_month_start()
    )
    next_month_result = allocation_service.create_allocations_for_specific_children(child_ids, get_next_month_start())

    total_created = current_month_result.created_count + next_month_result.created_count
    payment_enabled_count = len(payment_enabled_children)
    total_expected = payment_enabled_count * 2  # current month + next month for each payment-enabled child

    current_app.logger.info(
        f"Created allocations for family {family_id}: "
        f"Current month: {current_month_result.created_count} created, {current_month_result.skipped_count} skipped. "
        f"Next month: {next_month_result.created_count} created, {next_month_result.skipped_count} skipped."
    )

    # Log warning for partial creation
    if total_created < total_expected:
        current_app.logger.warning(
            f"Partial allocation creation for family {family_id}: {total_created}/{total_expected} created. "
            f"Current month: {current_month_result.created_count} created, {current_month_result.skipped_count} skipped, {current_month_result.error_count} errors. "
            f"Next month: {next_month_result.created_count} created, {next_month_result.skipped_count} skipped, {next_month_result.error_count} errors."
        )

    # Raise exception if complete failure
    if total_created == 0 and payment_enabled_count > 0:
        error_messages = current_month_result.errors + next_month_result.errors
        error_detail = f"No allocations were created. " + (
            f"Errors: {'; '.join(error_messages[:3])}"
            if error_messages
            else "No children matched the allocation criteria."
        )
        current_app.logger.error(
            f"Failed to create allocations for family {family_id}: {error_detail}. "
            f"Current month: {current_month_result.created_count} created, {current_month_result.error_count} errors. "
            f"Next month: {next_month_result.created_count} created, {next_month_result.error_count} errors."
        )
        abort(400, description=error_detail)


def process_family_invitation_mappings(family_data, children: list, family_id: int) -> None:
    """
    Process provider-child mappings from family invitation link.

    If the family has a link_id, finds the invitation and creates
    provider-child mappings for children that don't have a provider yet.

    Args:
        family_data: Family record from database
        children: List of child records
        family_id: Family ID for logging
    """

    link_id = Family.LINK_ID(family_data)
    if link_id is None:
        return  # No invitation to process

    invite: FamilyInvitation = FamilyInvitation.invitation_by_id(link_id).first()
    if invite is None:
        current_app.logger.warning(f"Family invitation with ID {link_id} not found")
        return

    provider_result = Provider.select_by_id(
        cols(Provider.ID, Child.join(Child.ID)), int(invite.provider_supabase_id)
    ).execute()
    provider = unwrap_or_abort(provider_result)
    if not provider:
        current_app.logger.warning(f"Provider {invite.provider_supabase_id} not found for invitation {link_id}")
        return

    extra_slots = MAX_CHILDREN_PER_PROVIDER - len(Child.unwrap(provider))

    for child in children:
        if extra_slots <= 0:
            break

        # Skip if child already has this provider
        child_has_provider = any(Provider.ID(p) == invite.provider_supabase_id for p in Provider.unwrap(child))
        if child_has_provider:
            continue

        ProviderChildMapping.query().insert(
            {
                ProviderChildMapping.CHILD_ID: Child.ID(child),
                ProviderChildMapping.PROVIDER_ID: invite.provider_supabase_id,
            }
        ).execute()
        extra_slots -= 1

    invite.record_accepted()
    db.session.add(invite)
    db.session.commit()
    current_app.logger.info(f"Created provider-child mappings for family {family_id} invitation {link_id}")


def process_provider_invitation_mappings(provider_data, provider_id: int) -> None:
    """
    Process family-child mappings from provider invitation link.

    If the provider has a link_id, finds the invitations and creates
    provider-child mappings for children that don't have a provider yet.

    Args:
        provider_data: Provider record from database
        provider_id: Provider ID for logging and mapping
    """

    link_id = Provider.LINK_ID(provider_data)
    if link_id is None:
        return  # No invitation to process

    invites: list[ProviderInvitation] = ProviderInvitation.invitations_by_id(link_id).all()
    if len(invites) == 0:
        current_app.logger.warning(f"Provider invitation with ID {link_id} not found")
        return

    for invite in invites[:MAX_CHILDREN_PER_PROVIDER]:
        child_result = Child.select_by_id(
            cols(Child.ID, Provider.join(Provider.ID)), int(invite.child_supabase_id)
        ).execute()
        child = unwrap_or_abort(child_result)

        if child is None:
            current_app.logger.warning(f"Child with ID {invite.child_supabase_id} not found.")
            continue

        # Skip if child already has a provider
        if len(Provider.unwrap(child)) > 0:
            continue

        ProviderChildMapping.query().insert(
            {
                ProviderChildMapping.CHILD_ID: invite.child_supabase_id,
                ProviderChildMapping.PROVIDER_ID: provider_id,
            }
        ).execute()
        invite.record_accepted()
        db.session.add(invite)

    db.session.commit()
    current_app.logger.info(f"Created family-child mappings for provider {provider_id} invitation {link_id}")
