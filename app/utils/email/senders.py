"""
Email template functions for various notification types.
"""

from dataclasses import dataclass

from flask import current_app

from app.enums.email_type import EmailType
from app.models import AllocatedCareDay
from app.models.attendance import Attendance
from app.supabase.columns import Language
from app.supabase.helpers import format_name
from app.supabase.tables import Child
from app.utils.date_utils import get_week_range
from app.utils.email.config import (
    get_from_email_external,
    get_internal_email_config,
)
from app.utils.email.core import send_email
from app.utils.email.templates import PaymentNotificationTemplate


@dataclass
class SystemMessageRow:
    title: str
    value: str


def html_link(link: str, text: str):
    return f"<a href='{link}' style='color: #0066cc; text-decoration: underline;'>{text}</a>"


def system_message(subject: str, description: str, rows: list[SystemMessageRow]):
    """Create a system message email template with a table of information."""
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
    """Send email notification for care days payment processing."""
    amount_dollars = amount_in_cents / 100

    from_email, to_emails = get_internal_email_config()

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
        email_type=EmailType.CARE_DAYS_PAYMENT,
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
    days: int,
    half_days: int,
    month: str,
) -> bool:
    """Send email notification for lump sum payment processing."""
    amount_dollars = amount_in_cents / 100

    from_email, to_emails = get_internal_email_config()

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
            title="Days",
            value=f"{days}",
        ),
        SystemMessageRow(
            title="Half Days",
            value=f"{half_days}",
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
        email_type=EmailType.LUMP_SUM_PAYMENT,
        context_data={
            "provider_id": provider_id,
            "child_id": child_id,
            "amount_cents": amount_in_cents,
            "days": days,
            "half_days": half_days,
            "month": month,
        },
        is_internal=True,
    )


def send_provider_invited_email(family_name: str, family_id: str, provider_email: str, ids: list[str]):
    """Send notification when a family invites a provider."""
    from_email, to_emails = get_internal_email_config()

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
        email_type=EmailType.PROVIDER_INVITED,
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
    """Send notification when a provider accepts an invite."""
    from_email, to_emails = get_internal_email_config()

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
        email_type=EmailType.PROVIDER_INVITE_ACCEPTED,
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
    """Send notification when a new payment rate is created."""
    from_email, to_emails = get_internal_email_config()

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
        email_type=EmailType.PAYMENT_RATE_CREATED,
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
    provider_language: Language = Language.ENGLISH,
) -> bool:
    """
    Sends a payment notification email to the provider when payment is completed.

    Args:
        provider_name: Provider's name
        provider_email: Provider's email address
        provider_id: Provider's external ID
        child_name: Child's name
        child_id: Child's external ID
        amount_cents: Payment amount in cents
        payment_method: Method used for payment (CARD or ACH)
        provider_language: Provider's preferred language (defaults to English)
    """
    from_email = get_from_email_external()

    current_app.logger.info(
        f"Sending payment notification to {provider_email} for provider ID: {provider_id}, "
        f"child ID: {child_id}, amount: ${amount_cents/100:.2f}, language: {provider_language}"
    )

    if not provider_email:
        current_app.logger.warning(f"Provider {provider_id} has no email address. Skipping notification.")
        return False

    # Use the template to build the email content in the provider's preferred language
    amount_dollars = amount_cents / 100
    subject = PaymentNotificationTemplate.get_subject(amount_dollars, provider_language)
    html_content = PaymentNotificationTemplate.build_html_content(
        provider_name=provider_name,
        child_name=child_name,
        amount_cents=amount_cents,
        payment_method=payment_method,
        language=provider_language,
    )

    return send_email(
        from_email=from_email,
        to_emails=[provider_email],
        subject=subject,
        html_content=html_content,
        email_type=EmailType.PAYMENT_NOTIFICATION,
        context_data={
            "provider_id": provider_id,
            "child_id": child_id,
            "amount_cents": amount_cents,
            "payment_method": payment_method,
            "language": provider_language.value,
        },
        is_internal=False,
    )


def send_family_invited_email(provider_name: str, provider_id: str, family_email: str, id: str):
    """Send notification when a provider invites a family."""
    from_email, to_emails = get_internal_email_config()

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
        email_type=EmailType.FAMILY_INVITED,
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
    """Send notification when a family accepts a provider's invite."""
    from_email, to_emails = get_internal_email_config()

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
    description = f"A new family invite has been accepted:"
    html_content = system_message(subject, description, rows)

    return send_email(
        from_email=from_email,
        to_emails=to_emails,
        subject=subject,
        html_content=html_content,
        email_type=EmailType.FAMILY_INVITE_ACCEPTED,
        context_data={
            "parent_name": parent_name,
            "parent_id": parent_id,
            "provider_name": provider_name,
            "provider_id": provider_id,
        },
        is_internal=True,
    )


def send_provider_attendance_completed_email(
    provider_name: str,
    provider_id: str,
    attendance_data: list[Attendance],
):
    from_email, to_emails = get_internal_email_config()

    current_app.logger.info(f"Sending accept invite request email to {to_emails} for provider ID: {provider_id}")

    rows = [
        SystemMessageRow(
            title="Provider Name",
            value=f"{provider_name} (ID: {provider_id})",
        )
    ]

    for attendance in attendance_data:
        week_start, week_end = get_week_range(attendance.week)
        rows.append(
            SystemMessageRow(
                title=f"{week_start.strftime('%B %d')} - {week_end.strftime('%B %d')}",
                value=f"<b>Full Days:</b> {attendance.provider_entered_full_days}, <b>Half Days:</b> {attendance.provider_entered_half_days}, <b>Child ID:</b> {attendance.child_supabase_id}",
            )
        )

    subject = "New Provider Attendance Notification"
    description = f"A new provider has submitted attendance for the following care days:"
    html_content = system_message(subject, description, rows)

    return send_email(
        from_email=from_email,
        to_emails=to_emails,
        subject=subject,
        html_content=html_content,
        email_type=EmailType.PROVIDER_ATTENDANCE_COMPLETED,
        context_data={
            "provider_id": provider_id,
            "provider_name": provider_name,
            "attendance_data": attendance_data,
        },
        is_internal=True,
    )


def send_family_attendance_completed_email(
    family_name: str,
    family_id: str,
    attendance_data: list[Attendance],
):
    from_email, to_emails = get_internal_email_config()

    current_app.logger.info(f"Sending attendance completed email to {to_emails} for family ID: {family_id}")

    rows = [
        SystemMessageRow(
            title="Family Name",
            value=f"{family_name} (ID: {family_id})",
        ),
    ]

    for attendance in attendance_data:
        week_start, week_end = get_week_range(attendance.week)
        rows.append(
            SystemMessageRow(
                title=f"{week_start.strftime('%B %d')} - {week_end.strftime('%B %d')}",
                value=f"<b>Full Days:</b> {attendance.family_entered_full_days}, <b>Half Days:</b> {attendance.family_entered_half_days}, <b>Provider ID:</b> {attendance.provider_supabase_id}, <b>Child ID:</b> {attendance.child_supabase_id}",
            )
        )

    subject = "New Family Attendance Notification"
    description = f"A new family attendance has been completed:"
    html_content = system_message(subject, description, rows)

    return send_email(
        from_email=from_email,
        to_emails=to_emails,
        subject=subject,
        html_content=html_content,
        email_type=EmailType.FAMILY_ATTENDANCE_COMPLETED,
        context_data={
            "family_id": family_id,
            "family_name": family_name,
            "attendance_data": attendance_data,
        },
        is_internal=True,
    )
