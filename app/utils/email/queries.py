"""
Email query functions for searching, filtering, and analyzing email logs.
"""

from sqlalchemy import String, cast, func, or_

from app.models.email_log import EmailLog


def get_failed_emails() -> list[EmailLog]:
    """Get all failed emails that can be retried."""
    return EmailLog.get_failed_emails()


def get_failed_internal_emails() -> list[EmailLog]:
    """Get all failed internal emails."""
    return EmailLog.get_failed_internal_emails()


def get_failed_external_emails() -> list[EmailLog]:
    """Get all failed external emails."""
    return EmailLog.get_failed_external_emails()


def search_emails_by_address(email_address: str) -> dict:
    """
    Search for all emails sent to or from a specific email address.
    Works correctly even if the email was sent to multiple recipients.

    Example: If an email was sent to ["user1@example.com", "user2@example.com"],
    searching for "user2@example.com" will find it.

    :param email_address: The email address to search for
    :return: Dictionary with sent and received emails
    """
    sent_emails = EmailLog.get_emails_by_sender(email_address)
    received_emails = EmailLog.get_emails_by_recipient(email_address)

    return {
        "sent_from": sent_emails,
        "sent_to": received_emails,
        "total_sent": len(sent_emails),
        "total_received": len(received_emails),
        "all_emails": sent_emails + received_emails,
    }


def get_email_history_for_provider(provider_email: str) -> list[EmailLog]:
    """Get all emails related to a provider."""
    return (
        EmailLog.query.filter(
            or_(
                EmailLog.from_email == provider_email,
                EmailLog.to_emails.contains([provider_email]),
                cast(EmailLog.context_data, String).ilike(f"%{provider_email}%"),
            )
        )
        .order_by(EmailLog.created_at.desc())
        .all()
    )


def get_recent_emails(limit: int = 100) -> list[EmailLog]:
    """Get the most recent emails."""
    return EmailLog.query.order_by(EmailLog.created_at.desc()).limit(limit).all()


def get_emails_by_domain(domain: str) -> list[EmailLog]:
    """
    Get all emails sent to any address at a specific domain.

    Example: get_emails_by_domain('@garycommunity.org')
    Will find all emails sent to anyone@garycommunity.org
    """
    return EmailLog.get_emails_by_any_recipient_contains(domain)


def get_broadcast_emails() -> list[EmailLog]:
    """Get all emails sent to multiple recipients (broadcasts)."""
    return (
        EmailLog.query.filter(func.json_array_length(EmailLog.to_emails) > 1).order_by(EmailLog.created_at.desc()).all()
    )


def get_email_stats() -> dict:
    """Get overall email statistics."""
    total = EmailLog.query.count()
    sent = EmailLog.query.filter(EmailLog.status == "sent").count()
    failed = EmailLog.query.filter(EmailLog.status == "failed").count()
    internal = EmailLog.query.filter(EmailLog.is_internal.is_(True)).count()
    external = EmailLog.query.filter(EmailLog.is_internal.is_(False)).count()

    return {
        "total_emails": total,
        "successful": sent,
        "failed": failed,
        "success_rate": f"{(sent/total*100):.1f}%" if total > 0 else "0%",
        "internal": internal,
        "external": external,
        "broadcasts": get_broadcast_emails(),
    }
