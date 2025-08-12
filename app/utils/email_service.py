from dataclasses import dataclass
from typing import Union, List
import sys
import traceback
from flask import current_app
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from app.sheets.helpers import KeyMap, format_name
from app.sheets.mappings import (
    get_provider,
    get_providers,
    get_child,
    get_children,
    ChildColumnNames,
    ProviderColumnNames,
)


def send_email(from_email: str, to_emails: Union[str, List[str]], subject: str, html_content: str) -> bool:
    """
    Send an email using SendGrid.

    :param from_email: Sender's email address.
    :param to_email: Recipient's email address.
    :param subject: Subject of the email.
    :param html_content: HTML content of the email.
    :return: True if the email was sent successfully, False otherwise.
    """
    try:
        environment = current_app.config.get("FLASK_ENV", "development")

        # Add environment prefix to subject for non-production environments
        subject_prefix = ""
        if environment != "production":
            subject_prefix = f"[{environment.upper()}] "

        message = Mail(
            from_email=from_email,
            to_emails=to_emails,
            subject=f"{subject_prefix}{subject}",
            html_content=html_content,
        )

        sendgrid_client = SendGridAPIClient(current_app.config.get("SENDGRID_API_KEY"))
        response = sendgrid_client.send(message)
        current_app.logger.info(f"SendGrid email sent with status code: {response.status_code}")
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
                "environment": environment,
                "from_email": from_email,
                "to_emails": to_emails,
                "subject": subject,
                "html_content": html_content,
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
                <a href="https://www.espn.com/nfl/story/_/id/45711952/2025-nfl-roster-ranking-starting-lineups-projection-32-teams" style="color: #0066cc; text-decoration: underline;">
                P.S. Check out the Saints (Lack of) Power Rankings
                </a>
            </p>
            <hr>
            <p style="font-size: 12px; color: #666;">This is an automated notification from the CAP portal system.</p>
        </body>
    </html>
    """


def send_payment_request_email(
    provider_name: str,
    google_sheets_provider_id: str,
    child_first_name: str,
    child_last_name: str,
    google_sheets_child_id: str,
    amount_in_cents: int,
    hours: float,
) -> bool:
    amount_dollars = amount_in_cents / 100

    from_email, to_emails = get_internal_emails()

    current_app.logger.info(
        f"Sending payment request email to {to_emails} for provider ID: {google_sheets_provider_id} from child ID: {google_sheets_child_id}"
    )

    subject = "New Payment Request Notification"
    description = f"A new payment request has been submitted through your payment system:"
    rows = [
        SystemMessageRow(
            title="Provider Name",
            value=f"{provider_name} (ID: {google_sheets_provider_id})",
        ),
        SystemMessageRow(
            title="Child Name",
            value=f"{child_first_name} {child_last_name} (ID: {google_sheets_child_id})",
        ),
        SystemMessageRow(
            title="Amount",
            value=f"${amount_dollars:.2f}",
        ),
        SystemMessageRow(
            title="Hours",
            value=str(hours),
        ),
    ]

    html_content = system_message(subject, description, rows)

    return send_email(
        from_email=from_email,
        to_emails=to_emails,
        subject=subject,
        html_content=html_content,
    )


def send_add_licensed_provider_email(
    license_number: str,
    provider_name: str,
    parent_name: str,
    parent_id: str,
    children: list[KeyMap],
):
    from_email, to_emails = get_internal_emails()

    current_app.logger.info(
        f"Sending add license provider request email to {to_emails} for family ID: {parent_id} for provider: {provider_name} for children: {[format_name(child) for child in children]}"
    )

    rows = [
        SystemMessageRow(
            title="License Number",
            value=license_number,
        ),
        SystemMessageRow(
            title="Provider Name",
            value=provider_name,
        ),
        SystemMessageRow(
            title=f"Parent Name (ID: {parent_id})",
            value=parent_name,
        ),
    ]

    for child in children:
        rows.append(
            SystemMessageRow(
                title="Child Name",
                value=f"{format_name(child)} (ID: {child.get(ChildColumnNames.ID)})",
            )
        )

    subject = "New Add Licensed Provider Request Notification"
    description = f"A new licensed provider request has been submitted:"
    html_content = system_message(subject, description, rows)

    return send_email(
        from_email=from_email,
        to_emails=to_emails,
        subject=subject,
        html_content=html_content,
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
    )


def send_submission_notification(provider_id, child_id, new_days, modified_days, removed_days):
    """Sends a submission notification email to the provider."""
    from_email = get_from_email_external()

    provider = get_provider(provider_id, get_providers())
    child = get_child(child_id, get_children())

    provider_name = provider.get(ProviderColumnNames.NAME) if provider else f"Provider {provider_id}"
    to_email = provider.get(ProviderColumnNames.EMAIL) if provider else None
    child_name = (
        f"{child.get(ChildColumnNames.FIRST_NAME)} {child.get(ChildColumnNames.LAST_NAME)}"
        if child
        else f"Child {child_id}"
    )

    current_app.logger.info(
        f"Sending submission notification to {to_email} for provider ID: {provider_id} and child ID: {child_id}"
    )

    if not to_email:
        current_app.logger.warning(f"Provider {provider_id} has no email address. Skipping notification.")
        return False

    subject = f"Care Day Submission Update for {child_name}"

    # Build the HTML content for the email
    html_content = f"""
    <html>
        <body style="font-family: sans-serif;">
            <h2>Care Day Submission Update</h2>
            <p>Hello {provider_name},</p>
            <p>This email is to notify you of an update to the care day submission for <strong>{child_name}</strong>.</p>
    """

    if new_days:
        html_content += "<h3>New Days Added:</h3><ul>"
        for day in new_days:
            html_content += f"<li>{day.date} - {day.type.value}</li>"
        html_content += "</ul>"

    if modified_days:
        html_content += "<h3>Days Modified:</h3><ul>"
        for day in modified_days:
            html_content += f"<li>{day.date} - Now: {day.type.value}</li>"
        html_content += "</ul>"

    if removed_days:
        html_content += "<h3>Days Removed:</h3><ul>"
        for day in removed_days:
            html_content += f"<li>{day.date} - {day.type.value}</li>"
        html_content += "</ul>"

    html_content += """
            <p>Thank you,</p>
            <p>The CAP Team</p>
            <hr>
            <p style="font-size: 12px; color: #666;">This is an automated notification from the CAP portal system.</p>
        </body>
    </html>
    """

    return send_email(
        from_email=from_email,
        to_emails=[to_email],
        subject=subject,
        html_content=html_content,
    )


def send_family_invite_accept_email(
    provider_name: str,
    provider_id: str,
    parent_name: str,
    parent_id: str,
    child_name: str,
    child_id: str,
):
    from_email, to_emails = get_internal_emails()

    current_app.logger.info(
        f"Sending accept invite request email to {to_emails} for provider ID: {provider_id} for family ID: {parent_id} for child ID: {child_id}"
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

    subject = "New Add Family Invite Accepted Notification"
    description = f"A new family invite request has been submitted:"
    html_content = system_message(subject, description, rows)

    return send_email(
        from_email=from_email,
        to_emails=to_emails,
        subject=subject,
        html_content=html_content,
    )
