import uuid
from datetime import datetime

from sqlalchemy.dialects.postgresql import UUID

from app.extensions import db


class BatchStatus:
    """Email batch status constants"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIALLY_FAILED = "partially_failed"
    FAILED = "failed"


class BulkEmailBatch(db.Model):
    """Model to track bulk email sends for attendance reminders and other campaigns"""

    __tablename__ = "bulk_email_batch"

    # Primary fields
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_name = db.Column(db.String(255), nullable=False)  # e.g., "Attendance Reminder 2025-01-22"
    batch_type = db.Column(db.String(100))  # e.g., "attendance_reminder", "notification"

    # What we CAN track without webhooks
    total_recipients = db.Column(db.Integer, nullable=False, default=0)
    successful_sends = db.Column(db.Integer, nullable=False, default=0)  # Accepted by SendGrid
    failed_sends = db.Column(db.Integer, nullable=False, default=0)  # Rejected/errored

    # Status tracking
    status = db.Column(db.String(50), nullable=False, default=BatchStatus.PENDING, index=True)
    initiated_by = db.Column(db.String(255))  # e.g., "attendance_cron", "admin_user"
    from_email = db.Column(db.String(255), nullable=False)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)

    # Additional context for attendance reminders
    metadata = db.Column(db.JSON)  # Can store: week_date, provider_count, family_count

    # Relationships
    email_logs = db.relationship("EmailLog", back_populates="bulk_batch", lazy="dynamic")

    def __repr__(self):
        return f"<BulkEmailBatch {self.batch_name} - {self.status}>"

    @property
    def success_rate(self) -> float:
        """Calculate the success rate of the batch"""
        if self.total_recipients == 0:
            return 0.0
        return (self.successful_sends / self.total_recipients) * 100

    @property
    def is_complete(self) -> bool:
        """Check if batch processing is complete"""
        return self.status in [BatchStatus.COMPLETED, BatchStatus.PARTIALLY_FAILED, BatchStatus.FAILED]

    def update_status(self):
        """Update batch status based on current counts"""
        if self.failed_sends == 0 and self.successful_sends == self.total_recipients:
            self.status = BatchStatus.COMPLETED
        elif self.successful_sends == 0:
            self.status = BatchStatus.FAILED
        elif self.failed_sends > 0:
            self.status = BatchStatus.PARTIALLY_FAILED

    def mark_started(self):
        """Mark the batch as started"""
        self.started_at = datetime.utcnow()
        self.status = BatchStatus.PROCESSING

    def mark_completed(self):
        """Mark the batch as completed"""
        self.completed_at = datetime.utcnow()
        self.update_status()

    def mark_all_sent(self, count: int, status_code: int = None):
        """Mark all emails in batch as successfully sent."""
        self.successful_sends = count
        self.failed_sends = 0
        self.update_status()

    def mark_all_failed(self, count: int):
        """Mark all emails in batch as failed."""
        self.successful_sends = 0
        self.failed_sends = count
        self.status = BatchStatus.FAILED

    @classmethod
    def get_recent_batches(cls, limit: int = 10):
        """Get recent batches ordered by creation date"""
        return cls.query.order_by(cls.created_at.desc()).limit(limit).all()

    @classmethod
    def get_attendance_batches(cls, limit: int = 10):
        """Get recent attendance reminder batches"""
        return cls.query.filter_by(batch_type="attendance_reminder").order_by(cls.created_at.desc()).limit(limit).all()

    def get_failed_emails(self):
        """Get all failed email logs in this batch"""
        from app.models.email_log import EmailStatus

        return self.email_logs.filter_by(status=EmailStatus.FAILED).all()

    def to_dict(self) -> dict:
        """Convert batch to dictionary for API responses"""
        return {
            "id": str(self.id),
            "batch_name": self.batch_name,
            "batch_type": self.batch_type,
            "total_recipients": self.total_recipients,
            "successful_sends": self.successful_sends,
            "failed_sends": self.failed_sends,
            "status": self.status,
            "success_rate": round(self.success_rate, 2),
            "initiated_by": self.initiated_by,
            "from_email": self.from_email,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata,
        }
