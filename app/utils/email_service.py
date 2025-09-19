import sys
import traceback
from dataclasses import dataclass
from typing import Union

import sentry_sdk
from flask import current_app
from sendgrid import Personalization, SendGridAPIClient, Substitution, To
from sendgrid.helpers.mail import Mail

from app.extensions import db
from app.models import AllocatedCareDay, EmailLog
from app.supabase.helpers import format_name
from app.supabase.tables import Child


def add_subject_prefix(subject: str):
    environment = current_app.config.get("FLASK_ENV", "development")
    prefix = ""

    if environment != "production":
        prefix = f"[{environment.upper()}]"

    return f"{prefix} {subject}"


def send_email_with_logging(
    from_email: str,
    to_emails: Union[str, list[str]],
    subject: str,
    html_content: str,
    from_name: str = "CAP Support",
    email_type: str = None,
    context_data: dict = None,
    is_internal: bool = False,
) -> bool:
    """
    Send an email using SendGrid with comprehensive logging.

    :param from_email: Sender's email address.
    :param to_emails: Recipient email address(es).
    :param subject: Subject of the email.
    :param html_content: HTML content of the email.
    :param from_name: Sender's display name.
    :param email_type: Type of email for categorization.
    :param context_data: Additional context for logging.
    :return: True if the email was sent successfully, False otherwise.
    """
    # Normalize to_emails to a list for consistent storage
    if isinstance(to_emails, str):
        to_emails_list = [to_emails]
    else:
        to_emails_list = to_emails

    # Convert UUIDs and other non-serializable objects in context_data to strings
    if context_data:
        serializable_context = {}
        for key, value in context_data.items():
            if hasattr(value, "__class__") and value.__class__.__name__ == "UUID":
                serializable_context[key] = str(value)
            elif isinstance(value, list):
                # Handle lists that might contain UUIDs
                serializable_context[key] = [
                    str(v) if hasattr(v, "__class__") and v.__class__.__name__ == "UUID" else v for v in value
                ]
            else:
                serializable_context[key] = value
    else:
        serializable_context = {}

    # Create EmailLog record
    email_log = EmailLog(
        from_email=from_email,
        to_emails=to_emails_list,
        subject=subject,
        html_content=html_content,
        from_name=from_name,
        email_type=email_type,
        context_data=serializable_context,
        is_internal=is_internal,
    )

    try:
        db.session.add(email_log)
        db.session.commit()

        # Send the email
        message = Mail(
            from_email=(from_email, from_name),
            to_emails=to_emails,
            subject=add_subject_prefix(subject),
            html_content=html_content,
        )

        sendgrid_client = SendGridAPIClient(current_app.config.get("SENDGRID_API_KEY"))
        response = sendgrid_client.send(message)

        # Extract message ID from response headers if available
        sendgrid_message_id = None
        if hasattr(response, "headers") and "X-Message-Id" in response.headers:
            sendgrid_message_id = response.headers["X-Message-Id"]

        # Mark as successful
        email_log.mark_as_sent(sendgrid_message_id=sendgrid_message_id, sendgrid_status_code=response.status_code)

        current_app.logger.info(f"SendGrid email sent with status code: {response.status_code}")
        return True

    except Exception as e:
        # Mark as failed and capture error details
        error_message = str(e)
        sendgrid_status_code = getattr(e, "status_code", None)

        email_log.mark_as_failed(error_message=error_message, sendgrid_status_code=sendgrid_status_code)

        # Log detailed error information
        exc_type, exc_value, _ = sys.exc_info()
        exc_traceback = traceback.format_exc()

        error_context = {
            "exc_traceback": exc_traceback,
            "exc_type": exc_type,
            "exc_value": exc_value,
            "from_email": from_email,
            "to_emails": to_emails,
            "subject": subject,
            "email_type": email_type,
            "email_log_id": str(email_log.id),
            "e.body": getattr(e, "body", None),
        }

        current_app.logger.error(f"Error sending email: {e}", extra=error_context)

        # Send error to Sentry for monitoring
        sentry_sdk.capture_exception(e, extra=error_context)

        return False


def send_email(
    from_email: str,
    to_emails: Union[str, list[str]],
    subject: str,
    html_content: str,
    from_name: str = "CAP Support",
    email_type: str = None,
    context_data: dict = None,
    is_internal: bool = False,
) -> bool:
    """
    Send an email using SendGrid with comprehensive logging.
    """
    return send_email_with_logging(
        from_email=from_email,
        to_emails=to_emails,
        subject=subject,
        html_content=html_content,
        from_name=from_name,
        email_type=email_type or "legacy",
        context_data=context_data or {},
        is_internal=is_internal,
    )


@dataclass
class BulkEmailData:
    email: str
    subject: str
    html_content: str


def bulk_send_emails(from_email: str, data: list[BulkEmailData]):
    try:
        message = Mail(from_email=from_email, to_emails=[], subject="[PLACEHOLDER]", html_content="{body}")

        for message_data in data:
            personalization = Personalization()
            personalization.add_to(To(message_data.email))
            personalization.subject = add_subject_prefix(message_data.subject)
            personalization.add_substitution(Substitution("{body}", message_data.html_content))

            message.add_personalization(personalization)

        sendgrid_client = SendGridAPIClient(current_app.config.get("SENDGRID_API_KEY"))
        response = sendgrid_client.send(message)
        current_app.logger.info(f"SendGrid emails sent with status code: {response.status_code}")
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
                "from_email": from_email,
                "data": data,
                "e.body": getattr(e, "body", None),
            },
        )
        current_app.logger.error(exc_traceback)
        return False


def get_from_email_internal() -> str:
    # Ensure the FROM_EMAIL_INTERNAL is set in the config
    if not current_app.config.get("FROM_EMAIL_INTERNAL"):
        raise ValueError("FROM_EMAIL_INTERNAL is not set in the configuration.")
    return str(current_app.config.get("FROM_EMAIL_INTERNAL"))


def get_from_email_external() -> str:
    # Ensure the FROM_EMAIL_EXTERNAL is set in the config
    if not current_app.config.get("FROM_EMAIL_EXTERNAL"):
        raise ValueError("FROM_EMAIL_EXTERNAL is not set in the configuration.")
    return str(current_app.config.get("FROM_EMAIL_EXTERNAL"))


def get_internal_emails() -> tuple[str, list[str]]:
    # Ensure email addresses are strings
    from_email = get_from_email_internal()
    to_emails = current_app.config.get("INTERNAL_EMAIL_RECIPIENTS", [])

    # Filter out empty strings from the list (in case of trailing commas in env var)
    to_emails = [email.strip() for email in to_emails if email.strip()]

    return from_email, to_emails


@dataclass
class SystemMessageRow:
    title: str
    value: str


def system_message(subject: str, description: str, rows: list[SystemMessageRow]):
    html_rows: list[str] = []
    for row in rows:
        html_rows.append(
            f"""
            <tr{' style="background-color: #f2f2f2;"' if len(html_rows) % 2 == 0 else ""}>
                <td style="padding: 10px; border: 1px solid #ddd;"><strong>{row.title}:</strong></td>
                <td style="padding: 10px; border: 1px solid #ddd;">{row.value}</td>
            </tr>"""
        )

    return f"""
    <html>
        <body>
            <h2>{subject}</h2>
            <p>{description}</p>
            <table style="border-collapse: collapse; width: 100%; margin: 20px 0;">
                {"".join(html_rows)}
            </table>
            <p>
                {html_link('https://www.espn.com/nfl/story/_/id/45711952/2025-nfl-roster-ranking-starting-lineups-projection-32-teams', 'P.S. Check out the Saints (Lack of) Power Rankings')}
            </p>
            <hr>
            <p style="font-size: 12px; color: #666;">This is an automated notification from the CAP portal system.</p>
        </body>
    </html>
    """


def send_care_days_payment_email(
    provider_name: str,
    provider_id: str,
    child_first_name: str,
    child_last_name: str,
    child_id: str,
    amount_in_cents: int,
    care_days: list[AllocatedCareDay],
) -> bool:
    amount_dollars = amount_in_cents / 100

    from_email, to_emails = get_internal_emails()

    current_app.logger.info(
        f"Sending payment processed notification to {to_emails} for provider ID: {provider_id} from child ID: {child_id}"
    )

    subject = "Care Days Payment Processed"
    description = f"Payment has been successfully processed for the following care days:"

    care_day_info = "<br>".join([f"{day.date} - {day.type.value} (${day.amount_cents / 100:.2f})" for day in care_days])

    if not care_day_info:
        current_app.logger.error("No care days provided for payment request email.")
        return False

    rows = [
        SystemMessageRow(
            title="Provider Name",
            value=f"{provider_name} (ID: {provider_id})",
        ),
        SystemMessageRow(
            title="Child Name",
            value=f"{child_first_name} {child_last_name} (ID: {child_id})",
        ),
        SystemMessageRow(
            title="Amount",
            value=f"${amount_dollars:.2f}",
        ),
        SystemMessageRow(
            title="Care Days Info",
            value=care_day_info,
        ),
    ]

    html_content = system_message(subject, description, rows)

    return send_email(
        from_email=from_email,
        to_emails=to_emails,
        subject=subject,
        html_content=html_content,
        email_type="care_days_payment",
        context_data={
            "provider_id": provider_id,
            "child_id": child_id,
            "amount_cents": amount_in_cents,
            "care_days_count": len(care_days),
        },
        is_internal=True,
    )


def send_lump_sum_payment_email(
    provider_name: str,
    provider_id: str,
    child_first_name: str,
    child_last_name: str,
    child_id: str,
    amount_in_cents: int,
    hours: float,
    month: str,
) -> bool:
    amount_dollars = amount_in_cents / 100

    from_email, to_emails = get_internal_emails()

    current_app.logger.info(
        f"Sending lump sum payment processed email to {to_emails} for provider ID: {provider_id} from child ID: {child_id}"
    )

    subject = "New Lump Sum Payment Notification"
    description = f"A new lump sum payment has been created:"

    rows = [
        SystemMessageRow(
            title="Provider Name",
            value=f"{provider_name} (ID: {provider_id})",
        ),
        SystemMessageRow(
            title="Child Name",
            value=f"{child_first_name} {child_last_name} (ID: {child_id})",
        ),
        SystemMessageRow(
            title="Amount",
            value=f"${amount_dollars:.2f}",
        ),
        SystemMessageRow(
            title="Hours",
            value=f"{hours:.2f}",
        ),
        SystemMessageRow(
            title="Month",
            value=month,
        ),
    ]

    html_content = system_message(subject, description, rows)

    return send_email(
        from_email=from_email,
        to_emails=to_emails,
        subject=subject,
        html_content=html_content,
        email_type="lump_sum_payment",
        context_data={
            "provider_id": provider_id,
            "child_id": child_id,
            "amount_cents": amount_in_cents,
            "hours": hours,
            "month": month,
        },
        is_internal=True,
    )


def send_provider_invited_email(family_name: str, family_id: str, provider_email: str, ids: list[str]):
    from_email, to_emails = get_internal_emails()

    current_app.logger.info(f"Sending invite sent request email to {to_emails} for family ID: {family_id}")

    rows = [
        SystemMessageRow(
            title="Family Name",
            value=family_name,
        ),
        SystemMessageRow(
            title="Provider Email",
            value=provider_email,
        ),
    ]

    for id in ids:
        rows.append(
            SystemMessageRow(
                title="Invite ID",
                value=id,
            )
        )

    subject = "Family Has Invited A Provider Notification"
    description = f"A family has invited a provider:"
    html_content = system_message(subject, description, rows)

    return send_email(
        from_email=from_email,
        to_emails=to_emails,
        subject=subject,
        html_content=html_content,
        email_type="provider_invited",
        context_data={
            "family_name": family_name,
            "family_id": family_id,
            "provider_email": provider_email,
            "invite_ids": ids,
        },
        is_internal=True,
    )


def send_provider_invite_accept_email(
    provider_name: str, provider_id: str, parent_name: str, parent_id: str, child_name: str, child_id: str
):
    from_email, to_emails = get_internal_emails()

    current_app.logger.info(
        f"Sending accept invite request email to {to_emails} for family ID: {parent_id} for provider ID: {provider_id} for child ID: {child_id}"
    )

    rows = [
        SystemMessageRow(
            title="Provider Name",
            value=f"{provider_name} (ID: {provider_id})",
        ),
        SystemMessageRow(
            title=f"Parent Name",
            value=f"{parent_name} (ID: {parent_id})",
        ),
        SystemMessageRow(
            title="Child Name",
            value=f"{child_name} (ID: {child_id})",
        ),
    ]

    subject = "New Add Provider Invite Accepted Notification"
    description = f"A new provider invite request has been submitted:"
    html_content = system_message(subject, description, rows)

    return send_email(
        from_email=from_email,
        to_emails=to_emails,
        subject=subject,
        html_content=html_content,
        email_type="provider_invite_accepted",
        context_data={
            "provider_name": provider_name,
            "provider_id": provider_id,
            "parent_name": parent_name,
            "parent_id": parent_id,
            "child_name": child_name,
            "child_id": child_id,
        },
        is_internal=True,
    )


def send_new_payment_rate_email(provider_id: str, child_id: str, half_day_rate_cents: int, full_day_rate_cents: int):
    from_email, to_emails = get_internal_emails()

    current_app.logger.info(
        f"Sending new payment rate email to {to_emails} for child ID: {child_id} for provider ID: {provider_id}"
    )

    rows = [
        SystemMessageRow(
            title="Provider ID",
            value=provider_id,
        ),
        SystemMessageRow(
            title="Child ID",
            value=child_id,
        ),
        SystemMessageRow(
            title="Half Day Rate",
            value=f"${half_day_rate_cents / 100:.2f}",
        ),
        SystemMessageRow(
            title="Full Day Rate",
            value=f"${full_day_rate_cents / 100:.2f}",
        ),
    ]

    subject = "New Payment Rate Created"
    description = f"A new payment rate has been created by provider {provider_id} for child {child_id}."
    html_content = system_message(subject, description, rows)

    return send_email(
        from_email=from_email,
        to_emails=to_emails,
        subject=subject,
        html_content=html_content,
        email_type="payment_rate_created",
        context_data={
            "provider_id": provider_id,
            "child_id": child_id,
            "half_day_rate_cents": half_day_rate_cents,
            "full_day_rate_cents": full_day_rate_cents,
        },
        is_internal=True,
    )


def send_payment_notification(
    provider_name: str,
    provider_email: str,
    provider_id: str,
    child_name: str,
    child_id: str,
    amount_cents: int,
    payment_method: str,
) -> bool:
    """
    Sends a payment notification email to the provider when payment is completed.

    Args:
        provider_id: Provider's external ID
        child_id: Child's external ID
        amount_cents: Payment amount in cents
        payment_method: Method used for payment (CARD or ACH)
        payment_id: Optional payment ID for reference
        month: Optional month string (YYYY-MM format)
    """
    from app.enums.payment_method import PaymentMethod

    from_email = get_from_email_external()

    current_app.logger.info(
        f"Sending payment notification to {provider_email} for provider ID: {provider_id}, "
        f"child ID: {child_id}, amount: ${amount_cents/100:.2f}"
    )

    if not provider_email:
        current_app.logger.warning(f"Provider {provider_id} has no email address. Skipping notification.")
        return False

    amount_dollars = amount_cents / 100
    subject = f"New Payment - ${amount_dollars:.2f}"

    # Format payment method for display
    payment_method_display = "Virtual Card" if payment_method == PaymentMethod.CARD else "Direct Deposit (ACH)"

    # Build the HTML content for the email
    html_content = f"""
    <html>
        <body style="font-family: sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #b53363; border-bottom: 2px solid #364f3f; padding-bottom: 10px;">
                    New Payment Processed
                </h2>
                
                <p>Hello {provider_name},</p>
                
                <p>We're pleased to inform you that a payment has been successfully processed for you.</p>
                
                <div style="background-color: #f8f9fa; border-left: 4px solid #364f3f; padding: 15px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #2c3e50;">Payment Details:</h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px 0;"><strong>Child:</strong></td>
                            <td style="padding: 8px 0;">{child_name}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0;"><strong>Amount:</strong></td>
                            <td style="padding: 8px 0; color: #364f3f; font-size: 18px;"><strong>${amount_dollars:.2f}</strong></td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0;"><strong>Payment Method:</strong></td>
                            <td style="padding: 8px 0;">{payment_method_display}</td>
                        </tr>
    """

    html_content += f"""
                    </table>
                </div>
                
                <div style="background-color: #C9D1CC; padding: 15px; margin: 20px 0; border-radius: 5px; color: #000000;">
                    <p style="margin: 0;"><strong>What's Next?</strong></p>
                    <ul style="margin: 10px 0 0 0; padding-left: 20px;">
    """

    if payment_method == PaymentMethod.CARD:
        html_content += """
                        <li>Funds have been loaded onto your virtual card</li>
                        <li>You can use your card immediately for purchases</li>
                        <li>Check your card balance in your Chek account</li>
        """
    else:  # ACH
        html_content += """
                        <li>Funds are being transferred to your bank account</li>
                        <li>Direct deposits typically arrive within 1-2 business days</li>
                        <li>You'll receive a confirmation once the transfer is complete</li>
        """

    html_content += """
                    </ul>
                </div>
                
                <p>If you have any questions about this payment, please reach out to our support team.</p>
                
                <p>Best regards,<br>
                The CAP Team</p>
                
                <hr style="margin-top: 30px; border: none; border-top: 1px solid #ddd;">
                <p style="font-size: 12px; color: #666; text-align: center;">
                    This is an automated notification from the CAP portal system.<br>
                </p>
            </div>
        </body>
    </html>
    """

    return send_email(
        from_email=from_email,
        to_emails=[provider_email],
        subject=subject,
        html_content=html_content,
        email_type="payment_notification",
        context_data={
            "provider_name": provider_name,
            "provider_email": provider_email,
            "provider_id": provider_id,
            "child_name": child_name,
            "child_id": child_id,
            "amount_cents": amount_cents,
            "payment_method": payment_method,
        },
    )


def send_family_invited_email(provider_name: str, provider_id: str, family_email: str, id: str):
    from_email, to_emails = get_internal_emails()

    current_app.logger.info(f"Sending invite sent request email to {to_emails} for provider ID: {provider_id}")

    rows = [
        SystemMessageRow(
            title="Provider Name",
            value=f"{provider_name} (ID: {provider_id})",
        ),
        SystemMessageRow(title="Family Email", value=family_email),
        SystemMessageRow(
            title="Invite ID",
            value=id,
        ),
    ]

    subject = "Provider Has Invited A Family Notification"
    description = f"A proivder has invited a family:"
    html_content = system_message(subject, description, rows)

    return send_email(
        from_email=from_email,
        to_emails=to_emails,
        subject=subject,
        html_content=html_content,
        email_type="family_invited",
        context_data={
            "provider_name": provider_name,
            "provider_id": provider_id,
            "family_email": family_email,
            "invite_id": id,
        },
        is_internal=True,
    )


def send_family_invite_accept_email(
    provider_name: str,
    provider_id: str,
    parent_name: str,
    parent_id: str,
    children: list[dict],
):
    from_email, to_emails = get_internal_emails()

    current_app.logger.info(
        f"Sending accept invite request email to {to_emails} for provider ID: {provider_id} for family ID: {parent_id} for child IDs: {[Child.ID(c) for c in children]}"
    )

    rows = [
        SystemMessageRow(
            title="Provider Name",
            value=f"{provider_name} (ID: {provider_id})",
        ),
        SystemMessageRow(
            title=f"Parent Name",
            value=f"{parent_name} (ID: {parent_id})",
        ),
    ]

    for child in children:
        rows.append(
            SystemMessageRow(
                title="Child Name",
                value=f"{format_name(child)} (ID: {Child.ID(child)})",
            )
        )

    subject = "New Add Family Invite Accepted Notification"
    description = f"A new family invite request has been submitted:"
    html_content = system_message(subject, description, rows)

    return send_email(
        from_email=from_email,
        to_emails=to_emails,
        subject=subject,
        html_content=html_content,
        email_type="family_invite_accepted",
        context_data={
            "provider_name": provider_name,
            "provider_id": provider_id,
            "parent_name": parent_name,
            "parent_id": parent_id,
            "children": [format_name(child) for child in children],
        },
        is_internal=True,
    )


def html_link(link: str, text: str):
    return f"<a href='{link}' style='color: #0066cc; text-decoration: underline;'>{text}</a>"


def retry_failed_email(email_log_id: str) -> bool:
    """
    Retry sending a failed email by email_log_id.

    :param email_log_id: The UUID of the EmailLog to retry
    :return: True if retry was successful, False otherwise
    """
    try:
        email_log = EmailLog.query.filter_by(id=email_log_id).first()

        if not email_log:
            current_app.logger.error(f"EmailLog with id {email_log_id} not found")
            return False

        if not email_log.is_failed:
            current_app.logger.warning(
                f"EmailLog {email_log_id} is not in failed status, current status: {email_log.status}"
            )
            return False

        current_app.logger.info(f"Retrying failed email {email_log_id} (attempt #{email_log.attempt_count + 1})")

        # Attempt to send the email again using the original parameters
        message = Mail(
            from_email=(email_log.from_email, email_log.from_name),
            to_emails=email_log.to_emails,
            subject=add_subject_prefix(email_log.subject),
            html_content=email_log.html_content,
        )

        sendgrid_client = SendGridAPIClient(current_app.config.get("SENDGRID_API_KEY"))
        response = sendgrid_client.send(message)

        # Extract message ID from response headers if available
        sendgrid_message_id = None
        if hasattr(response, "headers") and "X-Message-Id" in response.headers:
            sendgrid_message_id = response.headers["X-Message-Id"]

        # Update the same record as successful
        email_log.mark_as_sent(sendgrid_message_id=sendgrid_message_id, sendgrid_status_code=response.status_code)

        current_app.logger.info(f"Successfully retried email {email_log_id} with status code: {response.status_code}")
        return True

    except Exception as e:
        # Update the same record with the new failure
        error_message = str(e)
        sendgrid_status_code = getattr(e, "status_code", None)

        email_log.mark_as_failed(error_message=error_message, sendgrid_status_code=sendgrid_status_code)

        current_app.logger.error(f"Failed to retry email {email_log_id}: {e}")

        # Send error to Sentry
        sentry_sdk.capture_exception(
            e,
            extra={
                "email_log_id": email_log_id,
                "attempt_count": email_log.attempt_count,
                "email_type": email_log.email_type,
            },
        )

        return False


def get_failed_emails() -> list[EmailLog]:
    """Get all failed emails that can be retried."""
    return EmailLog.get_failed_emails()


def get_failed_internal_emails() -> list[EmailLog]:
    """Get all failed internal emails."""
    return EmailLog.get_failed_internal_emails()


def get_failed_external_emails() -> list[EmailLog]:
    """Get all failed external emails."""
    return EmailLog.get_failed_external_emails()


def retry_failed_emails_batch() -> dict:
    """
    Retry all failed emails in batch.

    :return: Dictionary with retry results
    """
    failed_emails = get_failed_emails()
    results = {"total_failed": len(failed_emails), "retry_successful": 0, "retry_failed": 0, "details": []}

    current_app.logger.info(f"Starting batch retry for {len(failed_emails)} failed emails")

    for email_log in failed_emails:
        try:
            success = retry_failed_email(str(email_log.id))
            if success:
                results["retry_successful"] += 1
                results["details"].append(
                    {"email_id": str(email_log.id), "email_type": email_log.email_type, "status": "success"}
                )
            else:
                results["retry_failed"] += 1
                results["details"].append(
                    {"email_id": str(email_log.id), "email_type": email_log.email_type, "status": "failed"}
                )
        except Exception as e:
            results["retry_failed"] += 1
            results["details"].append(
                {"email_id": str(email_log.id), "email_type": email_log.email_type, "status": "error", "error": str(e)}
            )
            current_app.logger.error(f"Error in batch retry for email {email_log.id}: {e}")

    current_app.logger.info(
        f"Batch retry completed: {results['retry_successful']} successful, {results['retry_failed']} failed"
    )
    return results
