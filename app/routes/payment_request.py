from flask import Blueprint, request, jsonify, abort, current_app
from app.extensions import db
from app.models.payment_request import PaymentRequest
from app.sheets.mappings import (
    get_provider_child_mappings,
    get_providers,
    get_children,
    get_child,
    get_provider,
    ProviderChildMappingColumnNames,
    ProviderColumnNames,
    ChildColumnNames,
)
from app.auth.decorators import auth_required, ClerkUserType
from app.utils.email_service import send_payment_request_email

bp = Blueprint("payment_request", __name__)


@bp.post("/payment-request")
@auth_required(ClerkUserType.FAMILY)
def create_payment_request():
    data = request.json

    google_sheets_provider_id = data.get("provider_id")
    amount_in_cents = data.get("amount_in_cents")
    hours = data.get("hours")
    google_sheets_child_id = data.get("child_id")

    # Validate required fields
    if not all(
        [google_sheets_provider_id, amount_in_cents, hours, google_sheets_child_id]
    ):
        abort(
            400,
            description="Missing required fields: provider_id, amount_in_cents, hours, child_id",
        )

    # Validate values
    if not isinstance(amount_in_cents, int) or amount_in_cents <= 0:
        abort(400, description="Amount in cents must be a positive integer.")
    if not isinstance(hours, (int, float)) or hours <= 0:
        abort(400, description="Hours must be a positive number.")
    if not isinstance(google_sheets_provider_id, int):
        abort(400, description="Google Sheets Provider ID must be an integer.")
    if not isinstance(google_sheets_child_id, int):
        abort(400, description="Google Sheets Child ID must be an integer.")

    # Verify child-provider connection using Google Sheets data
    provider_child_mappings = get_provider_child_mappings()
    providers = get_providers()
    children = get_children()

    # Find the specific child
    selected_child = get_child(google_sheets_child_id, children)
    if not selected_child:
        abort(
            404,
            description=f"Child with Google Sheets ID {google_sheets_child_id} not found.",
        )

    balance = selected_child.get(ChildColumnNames.BALANCE) or 0
    if balance < amount_in_cents / 100.0:
        abort(
            400,
            description=f"Child with Google Sheets ID {google_sheets_child_id} does not have enough balance to cover the payment request of {amount_in_cents} cents.",
        )

    # Find the specific provider
    selected_provider = get_provider(google_sheets_provider_id, providers)
    if not selected_provider:
        abort(
            404,
            description=f"Provider with Google Sheets ID {google_sheets_provider_id} not found.",
        )

    # Check if the child is connected to the provider
    is_connected = False
    for mapping in provider_child_mappings:
        if (
            mapping.get(ProviderChildMappingColumnNames.CHILD_ID)
            == google_sheets_child_id
            and mapping.get(ProviderChildMappingColumnNames.PROVIDER_ID)
            == google_sheets_provider_id
        ):
            is_connected = True
            break

    if not is_connected:
        abort(
            400,
            description=f"Child with Google Sheets ID {google_sheets_child_id} is not connected to provider with Google Sheets ID {google_sheets_provider_id}.",
        )

    provider_name = str(
        selected_provider.get(ProviderColumnNames.NAME) or "Unknown Provider"
    )
    child_first_name = str(selected_child.get(ChildColumnNames.FIRST_NAME) or "Unknown")
    child_last_name = str(selected_child.get(ChildColumnNames.LAST_NAME) or "Child")

    # Send SendGrid email
    email_sent_successfully = send_payment_request_email(
        provider_name=provider_name,
        google_sheets_provider_id=google_sheets_provider_id,
        child_first_name=child_first_name,
        child_last_name=child_last_name,
        google_sheets_child_id=google_sheets_child_id,
        amount_in_cents=amount_in_cents,
        hours=hours,
    )

    # Create and save payment request
    payment_request = PaymentRequest.new(
        google_sheets_provider_id=google_sheets_provider_id,
        google_sheets_child_id=google_sheets_child_id,
        amount_in_cents=amount_in_cents,
        hours=hours,
        email_sent_successfully=email_sent_successfully,
    )
    db.session.add(payment_request)
    db.session.commit()

    if not email_sent_successfully:
        current_app.logger.error(
            f"Failed to send payment request email for provider ID {google_sheets_provider_id} and child ID {google_sheets_child_id}.",
            extra={
                "google_sheets_provider_id": google_sheets_provider_id,
                "google_sheets_child_id": google_sheets_child_id,
            },
        )
        abort(500, description="Failed to send payment request email.")

    return (
        jsonify(
            {
                "message": "Payment request submitted successfully.",
                "payment_request_id": payment_request.id,
            }
        ),
        201,
    )
