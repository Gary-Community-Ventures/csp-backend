import uuid

from sqlalchemy.dialects.postgresql import JSONB, UUID

from ..extensions import db
from .mixins import TimestampMixin


class EmailStatus:
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class EmailRecord(db.Model, TimestampMixin):
    __tablename__ = "email_record"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Email Details
    from_email = db.Column(db.String(255), nullable=False, index=True)
    to_emails = db.Column(JSONB, nullable=False)  # Array of recipient email addresses
    subject = db.Column(db.String(500), nullable=False)  # Increased for prefixed subjects
    html_content = db.Column(db.Text, nullable=False)
    from_name = db.Column(db.String(100), nullable=False, default="CAP Support")

    # Status & Retry Tracking
    status = db.Column(db.String(20), nullable=False, default=EmailStatus.PENDING, index=True)
    attempt_count = db.Column(db.Integer, nullable=False, default=1)
    last_attempt_at = db.Column(db.DateTime(timezone=True), nullable=True)
    error_message = db.Column(db.Text, nullable=True)

    # SendGrid Response Data
    sendgrid_message_id = db.Column(db.String(100), nullable=True)
    sendgrid_status_code = db.Column(db.Integer, nullable=True)

    # Context & Metadata
    email_type = db.Column(db.String(50), nullable=True, index=True)  # "payment_notification", "provider_invite", etc.
    context_data = db.Column(JSONB, nullable=True)  # Additional context like provider_id, child_id, etc.
    is_internal = db.Column(db.Boolean, nullable=False, default=False, index=True)  # True if sent to internal team

    # Bulk Email Tracking
    bulk_batch_id = db.Column(UUID(as_uuid=True), db.ForeignKey("bulk_email_batch.id"), nullable=True)
    bulk_batch = db.relationship("BulkEmailBatch", back_populates="email_records")

    @property
    def recipients_count(self):
        """Get the number of recipients"""
        if isinstance(self.to_emails, list):
            return len(self.to_emails)
        return 1 if self.to_emails else 0

    @property
    def is_pending(self):
        """Check if email is pending"""
        return self.status == EmailStatus.PENDING

    @property
    def is_successful(self):
        """Check if email was sent successfully"""
        return self.status == EmailStatus.SENT

    @property
    def is_failed(self):
        """Check if email failed to send"""
        return self.status == EmailStatus.FAILED

    @classmethod
    def get_failed_emails(cls):
        """Get all failed emails that can be retried"""
        return cls.query.filter(cls.status == EmailStatus.FAILED)

    @classmethod
    def get_emails_by_type(cls, email_type: str):
        """Get all emails of a specific type"""
        return cls.query.filter(cls.email_type == email_type)

    @classmethod
    def get_internal_emails(cls):
        """Get all internal emails"""
        return cls.query.filter(cls.is_internal.is_(True))

    @classmethod
    def get_external_emails(cls):
        """Get all external emails"""
        return cls.query.filter(cls.is_internal.is_(False))

    @classmethod
    def get_failed_internal_emails(cls):
        """Get failed internal emails"""
        return cls.query.filter(cls.status == EmailStatus.FAILED, cls.is_internal.is_(True))

    @classmethod
    def get_failed_external_emails(cls):
        """Get failed external emails"""
        return cls.query.filter(cls.status == EmailStatus.FAILED, cls.is_internal.is_(False))

    @classmethod
    def get_emails_by_recipient(cls, recipient_email: str):
        """Get all emails where recipient_email appears in the to_emails array.
        Works correctly even when email is sent to multiple recipients.

        Example: If to_emails = ["user1@example.com", "user2@example.com", "user3@example.com"]
        Searching for "user2@example.com" will find this email.
        """
        # Use PostgreSQL's JSON array contains operator
        # This checks if the recipient_email is in the JSON array
        return cls.query.filter(cls.to_emails.op("@>")([recipient_email]))

    @classmethod
    def get_emails_by_any_recipient_contains(cls, search_term: str):
        """Get all emails where any recipient contains the search term (partial match).
        Useful for domain searches like '@example.com'

        Example: Searching for '@garycommunity.org' will find all emails
        sent to any email address at that domain.
        """
        from sqlalchemy import String, cast

        # Cast JSON to string and search within it
        return cls.query.filter(cast(cls.to_emails, String).ilike(f"%{search_term}%"))

    @classmethod
    def get_emails_containing_all_recipients(cls, recipient_list: list):
        """Get emails that include ALL specified recipients (but may include others too)"""
        # Use PostgreSQL's @> operator to check if to_emails contains all recipients
        return cls.query.filter(cls.to_emails.op("@>")(recipient_list))

    @classmethod
    def search_emails(cls, search_term: str):
        """Search emails by sender, recipients, or subject
        Returns emails where search_term appears in from_email, to_emails, or subject"""
        from sqlalchemy import String, cast, or_

        return cls.query.filter(
            or_(
                cls.from_email.ilike(f"%{search_term}%"),
                cls.subject.ilike(f"%{search_term}%"),
                cast(cls.to_emails, String).ilike(f"%{search_term}%"),
            )
        )

    def mark_as_sent(self, sendgrid_message_id=None, sendgrid_status_code=None):
        """Mark email as successfully sent"""
        self.status = EmailStatus.SENT
        self.sendgrid_message_id = sendgrid_message_id
        self.sendgrid_status_code = sendgrid_status_code
        self.last_attempt_at = db.func.current_timestamp()
        db.session.commit()

    def mark_as_failed(self, error_message=None, sendgrid_status_code=None):
        """Mark email as failed and increment attempt count"""
        self.status = EmailStatus.FAILED
        self.error_message = error_message
        self.sendgrid_status_code = sendgrid_status_code
        # Ensure attempt_count is not None before incrementing
        if self.attempt_count is None:
            self.attempt_count = 1
        else:
            self.attempt_count += 1
        self.last_attempt_at = db.func.current_timestamp()
        db.session.commit()

    def __repr__(self):
        internal_status = "Internal" if self.is_internal else "External"
        return f"<EmailRecord {self.id} - Status: {self.status} - Type: {self.email_type} - {internal_status} - Recipients: {self.recipients_count}>"
