from typing import Union, List

import sys
import traceback

from flask import current_app
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail


def send_email(
    from_email: str, to_emails: Union[str, List[str]], subject: str, html_content: str
) -> bool:
    """
    Send an email using SendGrid.

    :param from_email: Sender's email address.
    :param to_email: Recipient's email address.
    :param subject: Subject of the email.
    :param html_content: HTML content of the email.
    :return: True if the email was sent successfully, False otherwise.
    """
    try:
        envirnment = current_app.config.get("FLASK_ENV", "development")

        # Add environment prefix to subject for non-production environments
        subject_prefix = ""
        if envirnment != "production":
            subject_prefix = f"[{envirnment.upper()}] "

        message = Mail(
            from_email=from_email,
            to_emails=to_emails,
            subject=f"{subject_prefix}{subject}",
            html_content=html_content,
        )

        sendgrid_client = SendGridAPIClient(current_app.config.get("SENDGRID_API_KEY"))
        response = sendgrid_client.send(message)
        current_app.logger.info(
            f"SendGrid email sent with status code: {response.status_code}"
        )
        return True

    except Exception as e:
        exc_type, exc_value, _ = sys.exc_info()
        exc_traceback = traceback.format_exc()
        current_app.logger.error(
            f"Error sending email: {e}",
            extra={
                "exc_traceback": exc_traceback,
                "exc_type": exc_type,
                "exc_value": exc_value,
                "environment": envirnment,
                "from_email": from_email,
                "to_emails": to_emails,
                "subject": subject,
                "html_content": html_content,
                "e.body": getattr(e, "body", None),
            },
        )
        current_app.logger.error(exc_traceback)
        return False


def send_payment_request_email(
    provider_name: str,
    google_sheets_provider_id: int,
    child_first_name: str,
    child_last_name: str,
    google_sheets_child_id: int,
    amount_in_cents: int,
    hours: float,
) -> bool:
    amount_dollars = amount_in_cents / 100

    # Ensure email addresses are strings
    from_email = str(current_app.config.get("PAYMENT_REQUEST_SENDER_EMAIL"))
    to_emails = current_app.config.get("PAYMENT_REQUEST_RECIPIENT_EMAILS", [])
    
    # Filter out empty strings from the list (in case of trailing commas in env var)
    to_emails = [email.strip() for email in to_emails if email.strip()]

    current_app.logger.info(
        f"Sending payment request email to {to_emails} for provider ID: {google_sheets_provider_id} from child ID: {google_sheets_child_id}"
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
            <p>
                <a href="https://www.espn.com/nfl/story/_/id/45711952/2025-nfl-roster-ranking-starting-lineups-projection-32-teams" style="color: #0066cc; text-decoration: underline;">
                P.S. Check out the Saints Power Rankings
                </a>
            </p>
            <hr>
            <p style="font-size: 12px; color: #666;">This is an automated notification from your payment request system.</p>
        </body>
    </html>
    """

    return send_email(
        from_email=from_email,
        to_emails=to_emails,
        subject="New Payment Request Notification",
        html_content=html_content,
    )

def send_submission_notification(provider_id, child_id, new_days, modified_days, removed_days):
    """Placeholder for sending submission notification email."""
    current_app.logger.info(f"Sending submission notification for provider {provider_id}, child {child_id}")
    current_app.logger.info(f"New days: {new_days}")
    current_app.logger.info(f"Modified days: {modified_days}")
    current_app.logger.info(f"Removed days: {removed_days}")
    return True
