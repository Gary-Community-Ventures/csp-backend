from datetime import timedelta

import sentry_sdk
from flask import current_app

from app.constants import MAX_ALLOCATION_AMOUNT_CENTS
from app.supabase.helpers import cols, unwrap_or_error
from app.supabase.tables import Child
from app.utils.date_utils import get_current_month_start, get_next_month_start

from ..enums.care_day_type import CareDayType
from ..extensions import db
from .mixins import TimestampMixin
from .utils import get_care_day_cost


def get_allocation_amount(child_id: str) -> int:
    """Get the monthly allocation amount for a child"""

    child_results = Child.select_by_id(
        cols(Child.ID, Child.MONTHLY_ALLOCATION, Child.PRORATED_ALLOCATION), int(child_id)
    ).execute()
    child = unwrap_or_error(child_results)

    allocation_dollars = Child.MONTHLY_ALLOCATION(child)

    if allocation_dollars is None or allocation_dollars == 0:
        raise ValueError(
            f"Child {child_id} has invalid monthly allocation: must be greater than 0 (got {allocation_dollars})"
        )

    if Child.PRORATED_ALLOCATION(child) is None:
        raise ValueError(f"Child {child_id} has no prorated allocation set")

    # If no prior allocation exists, use prorated amount
    prior_allocation = MonthAllocation.query.filter_by(child_supabase_id=child_id).first()
    if not prior_allocation:
        allocation_dollars = Child.PRORATED_ALLOCATION(child)

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
    google_sheets_child_id = db.Column(db.String(64), nullable=True, index=True)
    child_supabase_id = db.Column(db.String(64), nullable=True, index=True)

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

    chek_transfer_id = db.Column(db.String(64), nullable=True, index=True)
    chek_transfer_date = db.Column(db.DateTime(timezone=True), nullable=True)

    __table_args__ = (db.UniqueConstraint("child_supabase_id", "date", name="unique_child_month"),)

    @property
    def selected_over_allocation(self):
        """Check if allocated care days exceed the monthly allocation"""
        return self.selected_cents > self.allocation_cents

    @property
    def selected_cents(self):
        """Total promised (allocated but not necessarily paid) from care days + lump sums.
        This prevents over-allocation but doesn't reduce the actual allocation."""
        return sum(day.amount_cents for day in self.care_days) + sum(
            lump_sum.amount_cents for lump_sum in self.lump_sums
        )

    @property
    def paid_cents(self):
        """Total actually paid out via successful payments.
        This is the real amount deducted from the allocation."""
        # Only count payments that actually succeeded
        return sum(payment.amount_cents for payment in self.payments)

    @property
    def remaining_unselected_cents(self):
        """How much budget is left to select (create new care days/lump sums).
        This prevents over-promising but doesn't reflect actual payment status."""
        return self.allocation_cents - self.selected_cents

    @property
    def remaining_unpaid_cents(self):
        """How much allocation is actually left to use.
        This is the real remaining allocation after successful payments."""
        return self.allocation_cents - self.paid_cents

    def can_add_care_day(self, day_type: CareDayType, provider_id: str) -> bool:
        """Check if we can add a care day of given type without over-allocating"""
        cents_amount = get_care_day_cost(day_type, provider_id=provider_id, child_id=self.child_supabase_id)
        return self.paid_cents + cents_amount <= self.allocation_cents

    def can_add_lump_sum(self, amount_cents: int) -> bool:
        """Check if we can add a lump sum without over-allocating"""
        return self.paid_cents + amount_cents <= self.allocation_cents

    @staticmethod
    def get_or_create_for_month(child_id: str, month_date: date):
        """Get existing allocation or create with default values"""
        from sqlalchemy.exc import IntegrityError

        # Normalize to first of month
        month_start = month_date.replace(day=1)

        # Prevent creating allocations for past months
        current_month_start = get_current_month_start()
        if month_start < current_month_start:
            raise ValueError(f"Cannot create allocation for a past month. {current_month_start} vs {month_start}")

        # Prevent creating allocations for months more than one month in the future
        next_month_start = get_next_month_start()
        if month_start > next_month_start:
            raise ValueError(f"Cannot create allocation for a month more than one month in the future.")

        # First, try to get existing allocation
        allocation = MonthAllocation.query.filter_by(child_supabase_id=child_id, date=month_start).first()

        if allocation:
            return allocation

        # Try to create new allocation, handling race conditions with database constraints
        try:
            # Get allocation amount from child data
            allocation_cents = get_allocation_amount(child_id)

            # Validate allocation doesn't exceed maximum
            if allocation_cents > MAX_ALLOCATION_AMOUNT_CENTS:
                raise ValueError(
                    f"Allocation amount ${allocation_cents / 100:.2f} exceeds maximum allowed allocation "
                    f"of ${MAX_ALLOCATION_AMOUNT_CENTS / 100:.2f} for child {child_id}"
                )

            # Create new allocation
            allocation = MonthAllocation(
                child_supabase_id=child_id,
                date=month_start,
                allocation_cents=allocation_cents,
            )

            db.session.add(allocation)
            db.session.commit()

            # Create the payment transfer once the allocation is created
            allocation.transfer_funds_for_allocation()
            db.session.commit()

            return allocation

        except IntegrityError:
            # Another process created the allocation, rollback and fetch it
            db.session.rollback()
            allocation = MonthAllocation.query.filter_by(child_supabase_id=child_id, date=month_start).first()
            if allocation:
                return allocation
            else:
                # This should be very rare - constraint violation but no record found
                raise RuntimeError(
                    f"Race condition detected but could not retrieve allocation for child {child_id} and month {month_start}"
                )

    def transfer_funds_for_allocation(self) -> bool:
        """
        Transfer funds for this allocation if needed.

        Returns:
            bool: True if transfer was created or already exists, False if creation failed
        """
        # Skip if allocation is zero or transfer already exists
        if self.allocation_cents <= 0:
            return True

        if self.chek_transfer_id:
            current_app.logger.info(
                f"Payment transaction already exists for allocation {self.id} "
                f"(child {self.child_supabase_id}, transfer {self.chek_transfer_id})"
            )
            return True

        # Create transfer
        try:
            transfer = current_app.payment_service.allocate_funds_to_family(
                child_id=self.child_supabase_id, amount=self.allocation_cents, date=self.date
            )

            if not transfer or not transfer.transfer or not transfer.transfer.id:
                current_app.logger.error(
                    f"Failed to create payment transfer for allocation {self.id}: Invalid transfer response"
                )
                return False

            # Update allocation with transfer details
            self.chek_transfer_id = transfer.transfer.id
            self.chek_transfer_date = transfer.transfer.created

            current_app.logger.info(
                f"Created transfer {self.chek_transfer_id} for allocation {self.id} "
                f"(child {self.child_supabase_id}, ${self.allocation_cents / 100:.2f})"
            )
            return True

        except Exception as e:
            sentry_sdk.capture_exception(e)
            current_app.logger.error(
                f"Failed to create transfer for allocation {self.id} " f"(child {self.child_supabase_id}): {e}"
            )
            return False

    @staticmethod
    def get_for_month(child_id: str, month_date: date):
        """Get existing allocation for a child and month, or None if not found"""
        # Normalize to first of month
        month_start = month_date.replace(day=1)

        allocation = MonthAllocation.query.filter_by(child_supabase_id=child_id, date=month_start).first()
        return allocation

    @property
    def locked_until_date(self) -> date:
        """Returns the last date (inclusive) for which a newly created care day would be immediately locked.

        Uses business timezone to determine the current lock status.
        """
        # Import here to avoid circular dependency
        from .allocated_care_day import get_locked_until_date

        return get_locked_until_date()

    @property
    def locked_past_date(self) -> date:
        """Returns the last date (inclusive) for which a newly created care day would be locked.

        Uses business timezone to determine the current lock status.
        """
        return self.locked_until_date + timedelta(days=8)

    def __repr__(self):
        return f"<MonthAllocation Child:{self.child_supabase_id} {self.date.strftime('%Y-%m')}"
