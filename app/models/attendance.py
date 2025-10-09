import uuid
from datetime import date, datetime, timedelta, timezone

from app.supabase.columns import ProviderType

from ..extensions import db
from .mixins import TimestampMixin


class Attendance(db.Model, TimestampMixin):
    id = db.Column(db.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    week = db.Column(db.Date, nullable=False, index=True)

    child_supabase_id = db.Column(db.String(64), nullable=True, index=True)
    family_entered_full_days = db.Column(db.Integer, nullable=True)
    family_entered_half_days = db.Column(db.Integer, nullable=True)
    family_entered_at = db.Column(db.DateTime(timezone=True), nullable=True)
    family_opened_at = db.Column(db.DateTime(timezone=True), nullable=True)

    provider_supabase_id = db.Column(db.String(64), nullable=True, index=True)
    provider_entered_full_days = db.Column(db.Integer, nullable=True)
    provider_entered_half_days = db.Column(db.Integer, nullable=True)
    provider_entered_at = db.Column(db.DateTime(timezone=True), nullable=True)
    provider_opened_at = db.Column(db.DateTime(timezone=True), nullable=True)

    child_google_sheet_id = db.Column(
        db.String(64), nullable=True, index=True
    )  # DEPRECATED: use child_supabase_id instead
    provider_google_sheet_id = db.Column(
        db.String(64), nullable=True, index=True
    )  # DEPRECATED: use provider_supabase_id instead
    family_entered_hours = db.Column(
        db.Integer, nullable=True
    )  # DEPRECATED: use family_entered_full_days and family_entered_half_days instead
    provider_entered_hours = db.Column(
        db.Integer, nullable=True
    )  # DEPRECATED: use provider_entered_full_days and provider_entered_half_days instead

    def __repr__(self):
        return f"<Attendance {self.id} - Child: {self.child_supabase_id} - Provider: {self.provider_supabase_id}>"

    @staticmethod
    def prev_week_date(weeks_ago: int = 1):
        today = datetime.now(timezone.utc).date()

        days_to_subtract = today.weekday() + 7 * weeks_ago

        return today - timedelta(days=days_to_subtract)

    @staticmethod
    def new(child_id: str, provider_id: str, date: date):
        return Attendance(week=date, child_supabase_id=child_id, provider_supabase_id=provider_id)

    def set_family_entered(self, full_days: int, half_days: int):
        self.family_entered_full_days = full_days
        self.family_entered_half_days = half_days
        self.family_entered_at = datetime.now(timezone.utc)

        return self

    def set_provider_entered(self, full_days: int, half_days: int):
        self.provider_entered_full_days = full_days
        self.provider_entered_half_days = half_days
        self.provider_entered_at = datetime.now(timezone.utc)

        return self

    def record_family_opened(self):
        if self.family_opened_at is not None:
            return self

        self.family_opened_at = datetime.now(timezone.utc)

        return self

    def record_provider_opened(self):
        if self.provider_opened_at is not None:
            return self

        self.provider_opened_at = datetime.now(timezone.utc)

        return self

    def center_is_due(self) -> bool:
        if self.provider_entered_full_days is not None and self.provider_entered_half_days is not None:
            return False

        today: date = datetime.now(timezone.utc).date()

        if today.year > self.week.year:
            return True

        if today.month > self.week.month:
            return True

        return False

    @classmethod
    def filter_by_child_ids(cls, child_ids: list[str]):
        return cls.filter_by_due_family_attendance().filter(cls.child_supabase_id.in_(child_ids))

    @classmethod
    def filter_by_provider_id(cls, provider_id: str):
        return cls.filter_by_due_provider_attendance().filter(cls.provider_supabase_id == provider_id)

    @classmethod
    def filter_by_overdue_attendance(cls, provider_id: str, child_id: str, provider_type: ProviderType):
        family_attendance_is_due = (  # NOTE: check if any attendance is due for the family
            cls.family_entered_full_days.is_(None)
            & cls.family_entered_half_days.is_(None)
            & cls.family_entered_hours.is_(None)  # NOTE: so old attendance doesn't show up
        )

        before_date = cls.prev_week_date()

        provider_attendance_is_due = (
            cls.provider_entered_full_days.is_(None)
            & cls.provider_entered_half_days.is_(None)
            & cls.provider_entered_hours.is_(None)  # NOTE: so old attendance doesn't show up
            & (cls.week < before_date)
        )

        base_query = cls.query.filter(
            cls.provider_supabase_id == provider_id,
            cls.child_supabase_id == child_id,
        )

        if provider_type == ProviderType.CENTER:
            return base_query.filter(family_attendance_is_due)

        return base_query.filter(family_attendance_is_due | provider_attendance_is_due)

    @classmethod
    def filter_by_due_family_attendance(cls):
        return cls.query.filter(
            cls.family_entered_full_days.is_(None),
            cls.family_entered_half_days.is_(None),
            cls.family_entered_hours.is_(None),  # NOTE: so old attendance doesn't show up
        )

    @classmethod
    def filter_by_due_provider_attendance(cls):
        return cls.query.filter(
            cls.provider_entered_full_days.is_(None),
            cls.provider_entered_half_days.is_(None),
            cls.provider_entered_hours.is_(None),  # NOTE: so old attendance doesn't show up
        )
