import uuid
from datetime import datetime, timezone

from ..extensions import db
from .mixins import TimestampMixin


class UserActivity(db.Model, TimestampMixin):
    """Tracks user activity by hour. One record per user per hour."""

    id = db.Column(db.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Stores the start of the hour (e.g., 2025-10-08 14:00:00+00:00)
    hour = db.Column(db.DateTime(timezone=True), nullable=False, index=True)

    # Either provider_supabase_id or family_supabase_id will be set
    provider_supabase_id = db.Column(db.String(64), nullable=True, index=True)
    family_supabase_id = db.Column(db.String(64), nullable=True, index=True)

    __table_args__ = (
        db.UniqueConstraint("provider_supabase_id", "hour", name="unique_provider_hour"),
        db.UniqueConstraint("family_supabase_id", "hour", name="unique_family_hour"),
    )

    def __repr__(self):
        user_id = self.provider_supabase_id or self.family_supabase_id
        return f"<UserActivity {self.id} - User: {user_id} - Hour: {self.hour}>"

    @staticmethod
    def truncate_to_hour(dt: datetime) -> datetime:
        """Truncate a datetime to the start of the hour."""
        return dt.replace(minute=0, second=0, microsecond=0)

    @classmethod
    def record_provider_activity(cls, provider_supabase_id: str, dt: datetime = None):
        """
        Record activity for a provider. Returns new activity object if created, None if already exists.

        Note: Caller is responsible for adding the returned activity to the session and committing.
        """
        if dt is None:
            dt = datetime.now(timezone.utc)

        hour = cls.truncate_to_hour(dt)

        # Check if activity already exists for this hour
        # Use no_autoflush to prevent premature flushing of pending objects
        with db.session.no_autoflush:
            activity = cls.query.filter_by(provider_supabase_id=provider_supabase_id, hour=hour).first()

        if activity is not None:
            return None  # Already exists, nothing to do

        # Create new activity record
        return cls(provider_supabase_id=provider_supabase_id, hour=hour)

    @classmethod
    def record_family_activity(cls, family_supabase_id: str, dt: datetime = None):
        """
        Record activity for a family. Returns new activity object if created, None if already exists.

        Note: Caller is responsible for adding the returned activity to the session and committing.
        """
        if dt is None:
            dt = datetime.now(timezone.utc)

        hour = cls.truncate_to_hour(dt)

        # Check if activity already exists for this hour
        # Use no_autoflush to prevent premature flushing of pending objects
        with db.session.no_autoflush:
            activity = cls.query.filter_by(family_supabase_id=family_supabase_id, hour=hour).first()

        if activity is not None:
            return None  # Already exists, nothing to do

        # Create new activity record
        return cls(family_supabase_id=family_supabase_id, hour=hour)
