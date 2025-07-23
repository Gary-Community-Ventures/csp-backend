from flask import current_app
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail


def send_payment_request_email(
    provider_name: str,
    google_sheets_provider_id: int,
    child_first_name: str,
    child_last_name: str,
    google_sheets_child_id: int,
    amount_in_cents: int,
    hours: float,
) -> bool:
    try:
        # Build the HTML content using KeyMap.get() correctly and ensure strings
        provider_name = str(provider_name or "Unknown Provider")
        child_first_name = str(child_first_name or "Unknown")
        child_last_name = str(child_last_name or "Child")
        amount_dollars = amount_in_cents / 100

        # Ensure email addresses are strings
        from_email = str(current_app.config.get("SENDGRID_SENDER_EMAIL"))
        to_email = str(current_app.config.get("PAYMENT_REQUEST_RECIPIENT_EMAIL"))

        current_app.logger.info(
            f"Sending payment request email to {to_email} for provider ID: {google_sheets_provider_id} from child ID: {google_sheets_child_id}"
        )

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
            html_content=html_content,
        )

        sendgrid_client = SendGridAPIClient(current_app.config.get("SENDGRID_API_KEY"))
        response = sendgrid_client.send(message)
        current_app.logger.info(
            f"SendGrid email sent with status code: {response.status_code}"
        )
        return True

    except Exception as e:
        current_app.logger.error(f"Error sending SendGrid email: {e}")
        if hasattr(e, "body"):
            current_app.logger.error(f"SendGrid error body: {e.body}")
        return False
