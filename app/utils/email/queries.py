"""
Email query functions for searching, filtering, and analyzing email records.
"""

from sqlalchemy import String, cast, or_

from app.models.email_record import EmailRecord


def get_failed_emails() -> list[EmailRecord]:
    """Get all failed emails that can be retried."""
    return EmailRecord.get_failed_emails()


def get_failed_internal_emails() -> list[EmailRecord]:
    """Get all failed internal emails."""
    return EmailRecord.get_failed_internal_emails()


def get_failed_external_emails() -> list[EmailRecord]:
    """Get all failed external emails."""
    return EmailRecord.get_failed_external_emails()


def search_emails_by_address(email_address: str) -> dict:
    """
    Search for all emails sent to or from a specific email address.
    Works correctly even if the email was sent to multiple recipients.

    Example: If an email was sent to ["user1@example.com", "user2@example.com"],
    searching for "user2@example.com" will find it.

    :param email_address: The email address to search for
    :return: Dictionary with sent and received emails
    """
    sent_emails = EmailRecord.get_emails_by_sender(email_address)
    received_emails = EmailRecord.get_emails_by_recipient(email_address)

    return {
        "sent_from": sent_emails,
        "sent_to": received_emails,
        "total_sent": len(sent_emails),
        "total_received": len(received_emails),
        "all_emails": sent_emails + received_emails,
    }


def get_email_history_for_provider(provider_email: str) -> list[EmailRecord]:
    """Get all emails related to a provider."""
    return (
        EmailRecord.query.filter(
            or_(
                EmailRecord.from_email == provider_email,
                EmailRecord.to_emails.contains([provider_email]),
                cast(EmailRecord.context_data, String).ilike(f"%{provider_email}%"),
            )
        )
        .order_by(EmailRecord.created_at.desc())
        .all()
    )


def get_recent_emails(limit: int = 100) -> list[EmailRecord]:
    """Get the most recent emails."""
    return EmailRecord.query.order_by(EmailRecord.created_at.desc()).limit(limit).all()


def get_emails_by_domain(domain: str) -> list[EmailRecord]:
    """
    Get all emails sent to any address at a specific domain.

    Example: get_emails_by_domain('@garycommunity.org')
    Will find all emails sent to anyone@garycommunity.org
    """
    return EmailRecord.get_emails_by_any_recipient_contains(domain)


def get_email_stats() -> dict:
    """Get overall email statistics."""
    total = EmailRecord.query.count()
    sent = EmailRecord.query.filter(EmailRecord.status == "sent").count()
    failed = EmailRecord.query.filter(EmailRecord.status == "failed").count()
    internal = EmailRecord.query.filter(EmailRecord.is_internal.is_(True)).count()
    external = EmailRecord.query.filter(EmailRecord.is_internal.is_(False)).count()

    return {
        "total_emails": total,
        "successful": sent,
        "failed": failed,
        "success_rate": f"{(sent/total*100):.1f}%" if total > 0 else "0%",
        "internal": internal,
        "external": external,
    }
