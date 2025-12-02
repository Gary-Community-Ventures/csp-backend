import zoneinfo
from datetime import date, datetime
from datetime import time as dt_time
from datetime import timedelta, timezone
from decimal import Decimal
from typing import Optional

from ..constants import BUSINESS_TIMEZONE
from ..enums.care_day_type import CareDayType
from ..extensions import db
from ..utils.date_utils import get_relative_week
from .mixins import TimestampMixin
from .month_allocation import MonthAllocation
from .utils import get_care_day_cost


def calculate_week_lock_date(date_in_week: Optional[date]) -> Optional[datetime]:
    """Calculate the lock date for any date in a week.

    Returns Monday at 23:59:59 (business timezone) of the week containing the given date.
    Care days are locked after this time passes.

    Args:
        date_in_week: Any date object within the week (must be date, not datetime)

    Returns:
        datetime: Monday at 23:59:59 of that week in business timezone

    Raises:
        TypeError: If date_in_week is a datetime object instead of a date
    """
    if not date_in_week:
        return None

    # Ensure we're working with a date object, not a datetime
    # Note: datetime is a subclass of date, so we check for datetime first
    if isinstance(date_in_week, datetime):
        raise TypeError(
            f"calculate_week_lock_date expects a date object, not datetime. "
            f"Got {type(date_in_week).__name__}. "
            f"Use .date() to extract the date from a datetime object."
        )

    monday = get_relative_week(0, date_in_week)

    # Create timezone-aware locked_date in business timezone (Monday at 23:59:59)
    business_tz = zoneinfo.ZoneInfo(BUSINESS_TIMEZONE)
    return datetime.combine(monday, dt_time(23, 59, 59), tzinfo=business_tz)


def get_locked_until_date() -> date:
    """Calculate the last date (inclusive) for which newly created care days would be immediately locked.

    This uses business timezone to determine whether we've passed the current week's lock time.

    Returns:
        date: Sunday of previous week if before Monday 23:59:59,
              Sunday of current week if after Monday 23:59:59
    """
    business_tz = zoneinfo.ZoneInfo(BUSINESS_TIMEZONE)
    now_business = datetime.now(business_tz)
    today_business = now_business.date()

    # Get the lock date for the current week
    current_week_lock_date = calculate_week_lock_date(today_business)

    current_monday = get_relative_week(0, today_business)

    if now_business > current_week_lock_date:
        # Past Monday 23:59:59 - all days in current week are locked
        return current_monday + timedelta(days=6)  # Sunday of current week
    else:
        # Before Monday 23:59:59 - days up to previous Sunday are locked
        return current_monday - timedelta(days=1)  # Sunday of previous week


class AllocatedCareDay(db.Model, TimestampMixin):
    """Individual allocated care day"""

    id = db.Column(db.Integer, primary_key=True)

    # Relationships
    care_month_allocation_id = db.Column(db.Integer, db.ForeignKey("month_allocation.id"), nullable=False)
    care_month_allocation = db.relationship(
        "MonthAllocation",
        back_populates="care_days",
        foreign_keys=[care_month_allocation_id],
    )
    month_allocation_with_deleted = db.relationship(
        "MonthAllocation",
        back_populates="all_care_days",
        foreign_keys=[care_month_allocation_id],
        overlaps="care_days,care_month_allocation",
    )

    # Care day details
    date = db.Column(db.Date, nullable=False, index=True)
    type = db.Column(db.Enum(CareDayType), nullable=False)

    # Calculated fields
    amount_cents = db.Column(db.Integer, nullable=False)

    # Provider info
    provider_google_sheets_id = db.Column(db.String(64), nullable=True, index=True)
    provider_supabase_id = db.Column(db.String(64), nullable=True, index=True)

    # Payment tracking
    payment_id = db.Column(
        db.UUID(as_uuid=True), db.ForeignKey("payment.id", name="fk_allocated_care_day_payment_id"), nullable=True
    )
    payment = db.relationship("Payment", back_populates="allocated_care_days")

    # Status tracking
    payment_distribution_requested = db.Column(db.Boolean, default=False)
    last_submitted_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Soft delete
    deleted_at = db.Column(db.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # Prevent duplicate care days for same allocation/provider/date (including soft deleted)
        db.UniqueConstraint(
            "care_month_allocation_id",
            "provider_supabase_id",
            "date",
            name="unique_allocation_provider_date",
        ),
    )

    @property
    def is_submitted(self):
        """Check if this care day is submitted"""
        return self.last_submitted_at is not None

    @property
    def day_count(self):
        """Return the day count based on type"""
        return Decimal("1.0") if self.type == CareDayType.FULL_DAY else Decimal("0.5")

    @property
    def needs_resubmission(self):
        """Check if day was modified after last submission"""
        if not self.last_submitted_at:
            return True  # Never submitted
        return self.updated_at > self.last_submitted_at

    @property
    def is_new(self):
        """Check if this is a brand new day since last submission"""
        return self.last_submitted_at is None

    @property
    def locked_date(self):
        """Calculate the locked date for this care day"""
        return calculate_week_lock_date(self.date)

    @property
    def is_locked(self):
        """Check if this care day is locked"""
        if not self.locked_date:
            return False

        # Use business timezone for logic
        business_tz = zoneinfo.ZoneInfo(BUSINESS_TIMEZONE)
        now_business = datetime.now(business_tz)

        return now_business > self.locked_date

    @property
    def is_deleted(self):
        """Check if this care day is soft deleted"""
        return self.deleted_at is not None

    def soft_delete(self):
        """Soft delete this care day"""
        self.deleted_at = datetime.now(timezone.utc)
        db.session.commit()

    def restore(self):
        """Restore a soft deleted care day"""
        self.deleted_at = None
        db.session.commit()

    def mark_as_submitted(self):
        """Mark this day as submitted to provider"""
        self.last_submitted_at = datetime.now(timezone.utc)

    @staticmethod
    def create_care_day(
        allocation: "MonthAllocation",
        provider_id: str,
        care_date: date,
        day_type: CareDayType,
    ):
        """Create a new care day with proper validation"""
        # Validate that care date is in the same month as the allocation
        if care_date.year != allocation.date.year or care_date.month != allocation.date.month:
            raise ValueError(
                f"Care date {care_date.isoformat()} must be in the same month as the allocation "
                f"({allocation.date.strftime('%B %Y')})"
            )

        # Prevent creating care days in the past (using business timezone)
        business_tz = zoneinfo.ZoneInfo(BUSINESS_TIMEZONE)
        today_business = datetime.now(business_tz).date()
        if care_date < today_business:
            raise ValueError("Cannot create a care day in the past.")

        # Check if allocation can handle this care day
        if not allocation.can_add_care_day(day_type, provider_id=provider_id):
            raise ValueError("Adding this care day would exceed monthly allocation")

        # Check for existing care day on this date
        existing = AllocatedCareDay.query.filter_by(
            care_month_allocation_id=allocation.id,
            date=care_date,
            provider_supabase_id=provider_id,
        ).first()

        if existing and not existing.is_deleted:
            raise ValueError("Care day already exists for this date")

        # If there's a soft-deleted one, restore and update it
        if existing and existing.is_deleted:
            existing.restore()
            existing.type = day_type
            existing.provider_supabase_id = provider_id
            existing.amount_cents = get_care_day_cost(
                day_type,
                provider_id=provider_id,
                child_id=allocation.child_supabase_id,
            )
            db.session.commit()
            return existing

        # Create new care day
        care_day = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_supabase_id=provider_id,
            date=care_date,
            type=day_type,
            amount_cents=get_care_day_cost(
                day_type,
                provider_id=provider_id,
                child_id=allocation.child_supabase_id,
            ),
        )

        # Prevent creating a care day that would be locked (using business timezone)
        business_tz = zoneinfo.ZoneInfo(BUSINESS_TIMEZONE)
        now_business = datetime.now(business_tz)
        if now_business > care_day.locked_date:
            raise ValueError("Cannot create a care day that would be locked.")

        db.session.add(care_day)
        db.session.commit()
        return care_day

    def to_dict(self):
        """Returns a dictionary representation of the AllocatedCareDay."""
        return {
            "id": self.id,
            "care_month_allocation_id": self.care_month_allocation_id,
            "date": self.date.isoformat(),
            "type": self.type,
            "amount_cents": self.amount_cents,
            "day_count": self.day_count,
            "provider_supabase_id": self.provider_supabase_id,
            "payment_distribution_requested": self.payment_distribution_requested,
            "last_submitted_at": (self.last_submitted_at.isoformat() if self.last_submitted_at else None),
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "locked_date": self.locked_date.isoformat() if self.locked_date else None,
            "is_locked": self.is_locked,
            "is_deleted": self.is_deleted,
            "needs_resubmission": self.needs_resubmission,
            "is_new": self.is_new,
            "delete_not_submitted": self.delete_not_submitted,
            "status": self.status,
        }

    @property
    def status(self):
        if self.payment_id:
            return "submitted"
        if self.delete_not_submitted:
            return "delete_not_submitted"
        if self.is_deleted:
            return "deleted"
        if self.is_new:
            return "new"
        if self.needs_resubmission:
            return "needs_resubmission"
        if self.last_submitted_at:
            return "submitted"
        return "unknown"

    @property
    def delete_not_submitted(self):
        """Check if this care day is previously submitted deleted but not submitted again"""
        return self.is_deleted and self.last_submitted_at is not None and self.last_submitted_at < self.deleted_at

    def __repr__(self):
        return f"<AllocatedCareDay {self.date} {self.type} - Provider {self.provider_supabase_id}>"
