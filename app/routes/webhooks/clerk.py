"""
Clerk webhook handlers.
"""

import base64
import hashlib
import hmac

from flask import abort, current_app, request

from app.auth.decorators import ClerkUserType
from app.routes.webhooks import bp
from app.supabase.columns import Language
from app.supabase.helpers import cols
from app.supabase.tables import Family, Provider
from app.utils.email.config import get_from_email_external
from app.utils.email.core import send_email
from app.utils.email.templates import ClerkInvitationTemplate


def verify_clerk_webhook(payload: bytes, headers: dict) -> bool:
    """
    Verify Clerk webhook signature using svix headers.

    Args:
        payload: Raw request body bytes
        headers: Request headers

    Returns:
        bool: True if signature is valid
    """
    webhook_secret = current_app.config.get("CLERK_WEBHOOK_SECRET")
    if not webhook_secret:
        current_app.logger.error("CLERK_WEBHOOK_SECRET not configured")
        return False

    # Get svix headers
    svix_id = headers.get("svix-id")
    svix_timestamp = headers.get("svix-timestamp")
    svix_signature = headers.get("svix-signature")

    if not all([svix_id, svix_timestamp, svix_signature]):
        current_app.logger.error("Missing svix headers")
        return False

    # Construct the signed content
    signed_content = f"{svix_id}.{svix_timestamp}.{payload.decode('utf-8')}"

    # Compute expected signature
    secret_bytes = webhook_secret.encode("utf-8")
    if webhook_secret.startswith("whsec_"):
        # Remove the whsec_ prefix and decode from base64
        secret_bytes = base64.b64decode(webhook_secret[6:])

    expected_signature = hmac.new(secret_bytes, signed_content.encode("utf-8"), hashlib.sha256).digest()

    # Svix signature format: "v1,signature1 v1,signature2"
    signatures = svix_signature.split(" ")

    for sig in signatures:
        if "," in sig:
            version, signature = sig.split(",", 1)
            if version == "v1":
                sig_bytes = base64.b64decode(signature)
                if hmac.compare_digest(sig_bytes, expected_signature):
                    return True

    current_app.logger.error("Invalid webhook signature")
    return False


@bp.post("/webhooks/clerk")
def clerk_webhook():
    """
    Handle Clerk webhook events.

    Documentation: https://clerk.com/docs/integrations/webhooks/overview
    """
    # Get raw payload for signature verification
    payload = request.get_data()

    # Verify webhook signature
    if not verify_clerk_webhook(payload, request.headers):
        current_app.logger.warning("Clerk webhook signature verification failed")
        abort(401, description="Invalid signature")

    # Parse the event
    try:
        event = request.get_json()
    except Exception as e:
        current_app.logger.error(f"Failed to parse Clerk webhook payload: {str(e)}")
        abort(400, description="Invalid JSON")

    event_type = event.get("type")
    current_app.logger.info(f"Received Clerk webhook: {event_type}")

    # Handle email.created event (for custom email delivery)
    if event_type == "email.created":
        return handle_email_created(event)

    # Return success for unhandled events
    return {"success": True, "message": f"Event {event_type} received but not handled"}, 200


def handle_email_created(event: dict):
    """
    Handle email.created webhook from Clerk.

    This is triggered when Clerk would have sent an email, but "Delivered by Clerk"
    is toggled OFF. We intercept this to send our own branded emails instead.
    """
    data = event.get("data", {})

    to_email = data.get("to_email_address")
    email_type = data.get("slug")  # e.g., "invitation"

    # For invitations, Clerk includes data about the invitation
    # We need to check if this is an invitation email
    if email_type != "invitation":
        current_app.logger.info(f"Received email.created for type: {email_type}, skipping")
        return {"success": True, "message": f"Email type {email_type} not handled"}, 200

    # Extract invitation data from the email data
    # Clerk's email.created webhook structure: data.data contains the email template variables
    data_obj = data.get("data", {}) or {}

    # The invitation URL is in data.data.action_url
    invitation_url = data_obj.get("action_url")

    # Extract user metadata - Clerk includes this in data.data.invitation.public_metadata
    invitation_obj = data_obj.get("invitation", {})
    public_metadata = invitation_obj.get("public_metadata", {})

    if not to_email:
        current_app.logger.error("No email address in email.created event")
        return {"success": False, "error": "Missing email address"}, 400

    if not invitation_url:
        current_app.logger.error(
            f"Missing invitation URL in email.created event - type: {email_type}, event type: {event.get('type')}"
        )
        return {"success": False, "error": "Missing invitation URL"}, 400

    # Extract user type and IDs from metadata
    user_types = public_metadata.get("types", [])
    family_id = public_metadata.get("family_id")
    provider_id = public_metadata.get("provider_id")

    current_app.logger.info(
        f"Processing Clerk invitation email - Types: {user_types}, "
        f"Family ID: {family_id}, Provider ID: {provider_id}"
    )

    # Determine if this is a family or provider invitation
    is_family = ClerkUserType.FAMILY.value in user_types
    is_provider = ClerkUserType.PROVIDER.value in user_types

    if is_family:
        return send_family_clerk_invitation_email(to_email, family_id, invitation_url)
    elif is_provider:
        return send_provider_clerk_invitation_email(to_email, provider_id, invitation_url)
    else:
        current_app.logger.warning(f"Unknown user type in invitation: {user_types}")
        return {"success": True, "message": "Unknown user type, skipping email"}, 200


def send_family_clerk_invitation_email(email: str, family_id: int, invitation_url: str):
    """
    Send custom Clerk invitation email to a family member.

    Args:
        email: Email address of the family member
        family_id: Supabase family ID
        invitation_url: Clerk invitation URL
    """
    from_email = get_from_email_external()

    # Fetch family data from Supabase to get language preference
    family_result = Family.select_by_id(cols(Family.LANGUAGE), family_id).execute()

    if not family_result.data:
        current_app.logger.warning(f"Family {family_id} not found in Supabase, using English as default")
        language = Language.ENGLISH
    else:
        family_data = family_result.data
        language = Family.LANGUAGE(family_data) or Language.ENGLISH

    current_app.logger.info(f"Sending Clerk family invitation for family {family_id} in {language.value}")

    subject = ClerkInvitationTemplate.get_subject(language)
    html_content = ClerkInvitationTemplate.get_family_invitation_content(invitation_url, language)

    success = send_email(
        from_email=from_email,
        to_emails=email,
        subject=subject,
        html_content=html_content,
        email_type="clerk_family_invitation",
        context_data={
            "family_id": family_id,
            "language": language.value,
        },
        is_internal=False,
    )

    if success:
        return {"success": True, "message": "Family Clerk invitation email sent"}, 200
    else:
        return {"success": False, "error": "Failed to send email"}, 500


def send_provider_clerk_invitation_email(email: str, provider_id: int, invitation_url: str):
    """
    Send custom Clerk invitation email to a provider.

    Args:
        email: Email address of the provider
        provider_id: Supabase provider ID
        invitation_url: Clerk invitation URL
    """
    from_email = get_from_email_external()

    # Fetch provider data from Supabase to get language preference
    provider_result = Provider.select_by_id(
        cols(Provider.PREFERRED_LANGUAGE, Provider.FIRST_NAME), provider_id
    ).execute()

    if not provider_result.data:
        current_app.logger.warning(f"Provider {provider_id} not found in Supabase, using English as default")
        language = Language.ENGLISH
        provider_name = None
    else:
        provider_data = provider_result.data
        language = Provider.PREFERRED_LANGUAGE(provider_data) or Language.ENGLISH
        provider_name = Provider.FIRST_NAME(provider_data)

    current_app.logger.info(f"Sending Clerk provider invitation for provider {provider_id} in {language.value}")

    subject = ClerkInvitationTemplate.get_subject(language)
    html_content = ClerkInvitationTemplate.get_provider_invitation_content(invitation_url, language, provider_name)

    success = send_email(
        from_email=from_email,
        to_emails=email,
        subject=subject,
        html_content=html_content,
        email_type="clerk_provider_invitation",
        context_data={
            "provider_id": provider_id,
            "language": language.value,
        },
        is_internal=False,
    )

    if success:
        return {"success": True, "message": "Provider Clerk invitation email sent"}, 200
    else:
        return {"success": False, "error": "Failed to send email"}, 500
