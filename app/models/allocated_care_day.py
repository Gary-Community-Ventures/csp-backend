from ..enums.care_day_type import CareDayType
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
    care_month_allocation = db.relationship("MonthAllocation", back_populates="care_days", foreign_keys=[care_month_allocation_id])
    month_allocation_with_deleted = db.relationship("MonthAllocation", back_populates="all_care_days", foreign_keys=[care_month_allocation_id], overlaps="care_days,care_month_allocation")

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

    locked_date = db.Column(db.DateTime, nullable=False)

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
    def is_new(self):
        """Check if this is a brand new day since last submission"""
        return self.last_submitted_at is None

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

    def mark_as_submitted(self):
        """Mark this day as submitted to provider"""
        self.last_submitted_at = db.func.current_timestamp()

    @staticmethod
    def create_care_day(
        allocation: "MonthAllocation",
        provider_id: int,
        care_date: date,
        day_type: CareDayType,
    ):
        """Create a new care day with proper validation"""
        # Prevent creating care days in the past
        if care_date < date.today():
            raise ValueError("Cannot create a care day in the past.")

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
        # Calculate and set locked_date
        days_since_monday = care_date.weekday()
        monday = care_date - timedelta(days=days_since_monday)
        calculated_locked_date = datetime.combine(monday, dt_time(23, 59, 59))

        # Prevent creating a care day that would be locked
        if datetime.now() > calculated_locked_date:
            raise ValueError("Cannot create a care day that would be locked.")

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
            locked_date=calculated_locked_date,
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
        return (
            self.is_deleted
            and self.last_submitted_at is not None
            and self.last_submitted_at < self.deleted_at
        )

    def __repr__(self):
        return f"<AllocatedCareDay {self.date} {self.type} - Provider {self.provider_google_sheets_id}>"
