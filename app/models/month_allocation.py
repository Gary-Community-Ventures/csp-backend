from datetime import date, datetime, timezone
from datetime import time as dt_time
from datetime import timedelta
import zoneinfo

from app.sheets.mappings import (
    ChildColumnNames,
    get_child,
    get_children,
)
from app.config import BUSINESS_TIMEZONE

from ..enums.care_day_type import CareDayType
from ..extensions import db
from .mixins import TimestampMixin
from .utils import get_care_day_cost


def get_allocation_amount(child_id: str) -> int:
    """Get the monthly allocation amount for a child"""

    child_data = get_child(child_id, get_children())
    allocation_dollars = child_data.get(ChildColumnNames.MONTHLY_ALLOCATION)

    # If no prior allocation exists, use prorated amount
    prior_allocation = MonthAllocation.query.filter_by(google_sheets_child_id=child_id).first()
    if not prior_allocation:
        allocation_dollars = child_data.get(ChildColumnNames.PRORATED_FIRST_MONTH_ALLOCATION)

    if allocation_dollars is None or allocation_dollars == "":
        raise ValueError(f"Child {child_id} does not have a valid monthly allocation amount {allocation_dollars}")

    return int(allocation_dollars * 100)


class MonthAllocation(db.Model, TimestampMixin):
    """Monthly allocation for a child"""

    id = db.Column(db.Integer, primary_key=True)

    # Month/Year as first day of month (e.g., 2024-03-01 for March 2024)
    date = db.Column(db.Date, nullable=False, index=True)

    # Allocation amounts
    allocation_cents = db.Column(db.Integer, nullable=False)

    # Child reference
    google_sheets_child_id = db.Column(db.String(64), nullable=False, index=True)

    # Relationships
    care_days = db.relationship(
        "AllocatedCareDay",
        back_populates="care_month_allocation",
        primaryjoin="and_(MonthAllocation.id==AllocatedCareDay.care_month_allocation_id, "
        "AllocatedCareDay.deleted_at.is_(None))",
        overlaps="all_care_days",
    )

    # Include soft-deleted care days for admin purposes
    all_care_days = db.relationship(
        "AllocatedCareDay", back_populates="month_allocation_with_deleted", overlaps="care_days,care_month_allocation"
    )

    lump_sums = db.relationship("AllocatedLumpSum", back_populates="care_month_allocation")

    __table_args__ = (db.UniqueConstraint("google_sheets_child_id", "date", name="unique_child_month"),)

    @property
    def over_allocation(self):
        """Check if allocated care days exceed the monthly allocation"""
        return self.allocated_cents > self.allocation_cents
    
    @property
    def over_paid(self):
        """Check if payments exceed what was allocated"""
        return self.paid_cents > self.allocated_cents

    @property
    def used_days(self):
        """Calculate total days used from active care days"""
        return sum(day.day_count for day in self.care_days)

    @property
    def allocated_cents(self):
        """Total allocated (promised) from care days + lump sums"""
        return sum(day.amount_cents for day in self.care_days) + sum(
            lump_sum.amount_cents for lump_sum in self.lump_sums
        )
    
    @property
    def paid_cents(self):
        """Total actually paid via successful payments"""
        return sum(
            payment.amount_cents 
            for payment in self.payments 
            if payment.has_successful_attempt
        )
    
    @property
    def used_cents(self):
        """Calculate total cents used from active care days (DEPRECATED: use allocated_cents)"""
        # Keep for backward compatibility
        return self.allocated_cents

    @property
    def remaining_to_allocate_cents(self):
        """How much budget is left to allocate (create care days/lump sums)"""
        return self.allocation_cents - self.allocated_cents
    
    @property
    def remaining_to_pay_cents(self):
        """How much allocated money is left to pay"""
        return self.allocated_cents - self.paid_cents

    @property
    def remaining_cents(self):
        """Calculate remaining cents available (DEPRECATED: use remaining_to_allocate_cents)"""
        # Keep for backward compatibility
        return self.remaining_to_allocate_cents

    def can_add_care_day(self, day_type: CareDayType, provider_id: str) -> bool:
        """Check if we can add a care day of given type without over-allocating"""
        cents_amount = get_care_day_cost(day_type, provider_id=provider_id, child_id=self.google_sheets_child_id)
        return self.used_cents + cents_amount <= self.allocation_cents

    def can_add_lump_sum(self, amount_cents: int) -> bool:
        """Check if we can add a lump sum without over-allocating"""
        return self.used_cents + amount_cents <= self.allocation_cents

    @staticmethod
    def get_or_create_for_month(child_id: str, month_date: date):
        """Get existing allocation or create with default values"""
        # Normalize to first of month
        month_start = month_date.replace(day=1)

        # Prevent creating allocations for past months (using business timezone)
        business_tz = zoneinfo.ZoneInfo(BUSINESS_TIMEZONE)
        today_business = datetime.now(business_tz).date()
        if month_start < today_business.replace(day=1):
            raise ValueError(f"Cannot create allocation for a past month. {today_business} vs {month_start}")

        # Prevent creating allocations for months more than one month in the future
        current_month_start = today_business.replace(day=1)
        next_month_start = (current_month_start + timedelta(days=32)).replace(day=1)  # Get first day of next month

        if month_start > next_month_start:
            raise ValueError(f"Cannot create allocation for a month more than one month in the future.")

        allocation = MonthAllocation.query.filter_by(google_sheets_child_id=child_id, date=month_start).first()

        if not allocation:
            # Get allocation amount from child data
            allocation_cents = get_allocation_amount(child_id)

            allocation = MonthAllocation(
                google_sheets_child_id=child_id,
                date=month_start,
                allocation_cents=allocation_cents,
            )
            db.session.add(allocation)
            db.session.commit()

        return allocation

    @staticmethod
    def get_for_month(child_id: str, month_date: date):
        """Get existing allocation for a child and month, or None if not found"""
        # Normalize to first of month
        month_start = month_date.replace(day=1)

        allocation = MonthAllocation.query.filter_by(google_sheets_child_id=child_id, date=month_start).first()
        return allocation

    @property
    def locked_until_date(self) -> date:
        """Returns the last date (inclusive) for which a newly created care day would be immediately locked."""
        # Use business timezone for logic
        business_tz = zoneinfo.ZoneInfo(BUSINESS_TIMEZONE)
        now_business = datetime.now(business_tz)
        today_business = now_business.date()
        
        # Calculate the Monday of the current week (in business timezone)
        current_monday = today_business - timedelta(days=today_business.weekday())
        # Calculate the end of day for the current Monday (in business timezone)
        current_monday_eod = datetime.combine(current_monday, dt_time(23, 59, 59), tzinfo=business_tz)

        if now_business > current_monday_eod:
            # If current time is past Monday EOD (business time), all days in current week are locked
            return current_monday + timedelta(days=6)  # Sunday of current week
        else:
            # If current time is not yet past Monday EOD (business time), days up to previous Sunday are locked
            return current_monday - timedelta(days=1)  # Sunday of previous week

    def __repr__(self):
        return f"<MonthAllocation Child:{self.google_sheets_child_id} {self.date.strftime('%Y-%m')}"
