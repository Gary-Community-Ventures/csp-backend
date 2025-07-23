from flask import Blueprint, request, jsonify, abort, current_app
from app.extensions import db
from app.models.payment_request import PaymentRequest
from app.sheets.mappings import get_provider_child_mappings, get_families, get_providers, get_children, get_child, get_provider, get_family, ProviderChildMappingColumnNames, ProviderColumnNames, ChildColumnNames, FamilyColumnNames
from app.auth.decorators import auth_required, ClerkUserType
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

bp = Blueprint("payment_request", __name__)


@bp.post("/payment-request")
@auth_required(ClerkUserType.FAMILY) # Assuming only families can request payments
def create_payment_request():
    data = request.json

    google_sheets_provider_id = data.get("provider_id")
    amount_in_cents = data.get("amount_in_cents")
    hours = data.get("hours")
    google_sheets_child_id = data.get("child_id")

    # Validate required fields
    if not all([google_sheets_provider_id, amount_in_cents, hours, google_sheets_child_id]):
        abort(400, description="Missing required fields: provider_id, amount_in_cents, hours, child_id")

    # Validate values
    if not isinstance(amount_in_cents, int) or amount_in_cents <= 0:
        abort(400, description="Amount in cents must be a positive integer.")
    if not isinstance(hours, (int, float)) or hours <= 0:
        abort(400, description="Hours must be a positive number.")
    if not isinstance(google_sheets_provider_id, int):
        abort(400, description="Provider ID must be an integer.")
    if not isinstance(google_sheets_child_id, int):
        abort(400, description="Child ID must be an integer.")

    # Verify child-provider connection using Google Sheets data
    provider_child_mappings = get_provider_child_mappings()
    providers = get_providers()
    children = get_children()

    # Find the specific child
    selected_child = get_child(google_sheets_child_id, children)
    if not selected_child:
        abort(404, description=f"Child with ID {google_sheets_child_id} not found.")

    # Find the specific provider
    selected_provider = get_provider(google_sheets_provider_id, providers)
    if not selected_provider:
        abort(404, description=f"Provider with ID {google_sheets_provider_id} not found.")

    # Check if the child is connected to the provider
    is_connected = False
    for mapping in provider_child_mappings:
        if mapping.get(ProviderChildMappingColumnNames.CHILD_ID) == google_sheets_child_id and mapping.get(ProviderChildMappingColumnNames.PROVIDER_ID) == google_sheets_provider_id:
            is_connected = True
            break

    if not is_connected:
        abort(400, description=f"Child with ID {google_sheets_child_id} is not connected to provider with ID {google_sheets_provider_id}.")

    # Create and save payment request
    payment_request = PaymentRequest.new(
        google_sheets_provider_id=google_sheets_provider_id,
        google_sheets_child_id=google_sheets_child_id,
        amount_in_cents=amount_in_cents,
        hours=hours,
    )
    db.session.add(payment_request)
    db.session.commit()

    # Send SendGrid email
    try:
        # Build the HTML content using KeyMap.get() correctly and ensure strings
        provider_name = str(selected_provider.get(ProviderColumnNames.NAME) or "Unknown Provider")
        child_first_name = str(selected_child.get(ChildColumnNames.FIRST_NAME) or "Unknown")
        child_last_name = str(selected_child.get(ChildColumnNames.LAST_NAME) or "Child")
        amount_dollars = amount_in_cents / 100
        
        # Ensure email addresses are strings
        from_email = str(current_app.config.get("SENDGRID_SENDER_EMAIL"))
        to_email = str(current_app.config.get("PAYMENT_REQUEST_RECIPIENT_EMAIL"))
        
        current_app.logger.info(f"From email: '{from_email}'")
        current_app.logger.info(f"To email: '{to_email}'")
        current_app.logger.info(f"Provider name: '{provider_name}'")
        current_app.logger.info(f"Child name: '{child_first_name} {child_last_name}'")
        
        html_content = f"""
        <html>
            <body>
                <h2>Payment Request Notification</h2>
                <p>Hello,</p>
                <p>A new payment request has been submitted through your payment system:</p>
                <table style="border-collapse: collapse; width: 100%; margin: 20px 0;">
                    <tr style="background-color: #f2f2f2;">
                        <td style="padding: 10px; border: 1px solid #ddd;"><strong>Provider Name:</strong></td>
                        <td style="padding: 10px; border: 1px solid #ddd;">{provider_name} (ID: {google_sheets_provider_id})</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border: 1px solid #ddd;"><strong>Child Name:</strong></td>
                        <td style="padding: 10px; border: 1px solid #ddd;">{child_first_name} {child_last_name} (ID: {google_sheets_child_id})</td>
                    </tr>
                    <tr style="background-color: #f2f2f2;">
                        <td style="padding: 10px; border: 1px solid #ddd;"><strong>Amount:</strong></td>
                        <td style="padding: 10px; border: 1px solid #ddd;">${amount_dollars:.2f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border: 1px solid #ddd;"><strong>Hours:</strong></td>
                        <td style="padding: 10px; border: 1px solid #ddd;">{hours}</td>
                    </tr>
                </table>
                <p>Please process this payment request at your earliest convenience.</p>
                <p>Best regards,<br>Your Payment System</p>
                <hr>
                <p style="font-size: 12px; color: #666;">This is an automated notification from your payment request system.</p>
            </body>
        </html>
        """
        
        message = Mail(
            from_email=from_email,
            to_emails=to_email,
            subject="New Payment Request",
            html_content=html_content
        )
        
        sendgrid_client = SendGridAPIClient(current_app.config.get("SENDGRID_API_KEY"))
        response = sendgrid_client.send(message)
        current_app.logger.info(f"SendGrid email sent with status code: {response.status_code}")
        
    except Exception as e:
        current_app.logger.error(f"Error sending SendGrid email: {e}")
        if hasattr(e, 'body'):
            current_app.logger.error(f"SendGrid error body: {e.body}")

    return jsonify({"message": "Payment request submitted successfully.", "payment_request_id": payment_request.id}), 201
