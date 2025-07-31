from .enums import CareDayType
from ..extensions import db
from .mixins import TimestampMixin
from datetime import datetime, timedelta, date, time as dt_time
from decimal import Decimal
from .month_allocation import MonthAllocation
from .utils import get_care_day_cost


class AllocatedCareDay(db.Model, TimestampMixin):
    """Individual allocated care day"""

    id = db.Column(db.Integer, primary_key=True)

    # Relationships
    care_month_allocation_id = db.Column(
        db.Integer, db.ForeignKey("month_allocation.id"), nullable=False
    )

    # Care day details
    date = db.Column(db.Date, nullable=False, index=True)
    type = db.Column(db.Enum(CareDayType), nullable=False)

    # Calculated fields
    amount_cents = db.Column(db.Integer, nullable=False)

    # Provider info
    provider_google_sheets_id = db.Column(db.Integer, nullable=False, index=True)

    # Status tracking
    payment_distribution_requested = db.Column(db.Boolean, default=False)
    last_submitted_at = db.Column(db.DateTime, nullable=True)

    # Soft delete
    deleted_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        # Prevent duplicate care days for same allocation/date (including soft deleted)
        db.UniqueConstraint(
            "care_month_allocation_id", "date", name="unique_allocation_date"
        ),
    )

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
    def is_new_since_submission(self):
        """Check if this is a brand new day since last submission"""
        return self.last_submitted_at is None

    def mark_as_submitted(self):
        """Mark this day as submitted to provider"""
        self.last_submitted_at = db.func.current_timestamp()

    @property
    def locked_date(self):
        """Calculate when this care day locks (Monday 11:59:59 PM of the week)"""
        days_since_monday = self.date.weekday()
        monday = self.date - timedelta(days=days_since_monday)
        return datetime.combine(monday, dt_time(23, 59, 59))

    @property
    def is_locked(self):
        """Check if this care day is locked"""
        return datetime.now() > self.locked_date

    @property
    def is_deleted(self):
        """Check if this care day is soft deleted"""
        return self.deleted_at is not None

    def soft_delete(self):
        """Soft delete this care day"""
        self.deleted_at = datetime.utcnow()
        db.session.commit()

    def restore(self):
        """Restore a soft deleted care day"""
        self.deleted_at = None
        db.session.commit()

    @staticmethod
    def create_care_day(
        allocation: "MonthAllocation",
        provider_id: int,
        care_date: date,
        day_type: CareDayType,
    ):
        """Create a new care day with proper validation"""
        # Check if allocation can handle this care day
        if not allocation.can_add_care_day(day_type, provider_id=provider_id):
            raise ValueError("Adding this care day would exceed monthly allocation")

        # Check for existing care day on this date
        existing = AllocatedCareDay.query.filter_by(
            care_month_allocation_id=allocation.id, date=care_date
        ).first()

        if existing and not existing.is_deleted:
            raise ValueError("Care day already exists for this date")

        # If there's a soft-deleted one, restore and update it
        if existing and existing.is_deleted:
            existing.restore()
            existing.type = day_type
            existing.provider_google_sheets_id = provider_id
            existing.amount_cents = get_care_day_cost(
                day_type,
                provider_id=provider_id,
                child_id=allocation.google_sheets_child_id,
            )
            existing.last_submitted_at = datetime.utcnow()
            db.session.commit()
            return existing

        # Create new care day
        care_day = AllocatedCareDay(
            care_month_allocation_id=allocation.id,
            provider_google_sheets_id=provider_id,
            date=care_date,
            type=day_type,
            amount_cents=get_care_day_cost(
                day_type,
                provider_id=provider_id,
                child_id=allocation.google_sheets_child_id,
            ),
        )

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
            "provider_google_sheets_id": self.provider_google_sheets_id,
            "payment_distribution_requested": self.payment_distribution_requested,
            "last_submitted_at": (
                self.last_submitted_at.isoformat() if self.last_submitted_at else None
            ),
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "is_locked": self.is_locked,
            "is_deleted": self.is_deleted,
            "needs_resubmission": self.needs_resubmission,
            "is_new_since_submission": self.is_new_since_submission,
        }

    def __repr__(self):
        return f"<AllocatedCareDay {self.date} {self.type} - Provider {self.provider_google_sheets_id}>"
