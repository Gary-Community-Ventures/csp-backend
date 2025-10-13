import uuid
from datetime import datetime, timezone

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
    to_emails = db.Column(db.ARRAY(db.String(255)), nullable=False)  # Array of recipient email addresses
    subject = db.Column(db.String(500), nullable=False)  # Increased for prefixed subjects
    html_content = db.Column(db.Text, nullable=False)
    from_name = db.Column(db.String(100), nullable=False, default="")

    # Status & Retry Tracking
    status = db.Column(db.String(20), nullable=False, default=EmailStatus.PENDING, index=True)
    attempt_count = db.Column(db.Integer, nullable=False, default=1)
    last_attempt_at = db.Column(db.DateTime(timezone=True), nullable=True)
    error_message = db.Column(db.Text, nullable=True)

    # Email Provider Data
    email_provider = db.Column(db.String(50), nullable=True, index=True)  # "sendgrid", "postmark", etc.
    provider_message_id = db.Column(db.String(100), nullable=True, index=True)  # Message ID from email provider
    provider_status_code = db.Column(db.Integer, nullable=True)  # HTTP status code from provider

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
        return cls.query.filter(cls.to_emails.contains([recipient_email]))

    def mark_as_sent(
        self, provider_message_id=None, provider_status_code=None, sendgrid_message_id=None, sendgrid_status_code=None
    ):
        """Mark email as successfully sent

        Args:
            provider_message_id: Message ID from the email provider
            provider_status_code: HTTP status code from the provider
            sendgrid_message_id: (Deprecated) Use provider_message_id instead
            sendgrid_status_code: (Deprecated) Use provider_status_code instead
        """
        self.status = EmailStatus.SENT

        # Support both new and legacy parameter names
        self.provider_message_id = provider_message_id or sendgrid_message_id
        self.provider_status_code = provider_status_code or sendgrid_status_code

        self.last_attempt_at = datetime.now(timezone.utc)

    def mark_as_failed(self, error_message=None, provider_status_code=None, sendgrid_status_code=None):
        """Mark email as failed and increment attempt count

        Args:
            error_message: Error message describing the failure
            provider_status_code: HTTP status code from the provider
            sendgrid_status_code: (Deprecated) Use provider_status_code instead
        """
        self.status = EmailStatus.FAILED
        self.error_message = error_message

        # Support both new and legacy parameter names
        self.provider_status_code = provider_status_code or sendgrid_status_code

        self.last_attempt_at = datetime.now(timezone.utc)

    def __repr__(self):
        internal_status = "Internal" if self.is_internal else "External"
        return f"<EmailRecord {self.id} - Status: {self.status} - Type: {self.email_type} - {internal_status} - Recipients: {self.recipients_count}>"
