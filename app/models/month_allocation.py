from ..enums.care_day_type import CareDayType
from ..extensions import db
from .mixins import TimestampMixin
from datetime import datetime, date, timedelta, time as dt_time
from .utils import get_care_day_cost
from app.sheets.mappings import (
    ChildColumnNames,
    get_child,
    get_children,
)


def get_allocation_amount(child_id: int) -> int:
    """Get the monthly allocation amount for a child"""

    child_data = get_child(child_id, get_children())
    allocation_dollars = child_data.get(ChildColumnNames.MONTHLY_ALLOCATION)

    # If no prior allocation exists, use prorated amount
    prior_allocation = MonthAllocation.query.filter_by(
        google_sheets_child_id=child_id
    ).first()
    if not prior_allocation:
        allocation_dollars = child_data.get(
            ChildColumnNames.PRORATED_FIRST_MONTH_ALLOCATION
        )

    if allocation_dollars is None or allocation_dollars == "":
        raise ValueError(
            f"Child {child_id} does not have a valid monthly allocation amount {allocation_dollars}"
        )

    return int(allocation_dollars * 100)


class MonthAllocation(db.Model, TimestampMixin):
    """Monthly allocation for a child"""

    id = db.Column(db.Integer, primary_key=True)

    # Month/Year as first day of month (e.g., 2024-03-01 for March 2024)
    date = db.Column(db.Date, nullable=False, index=True)

    # Allocation amounts
    allocation_cents = db.Column(db.Integer, nullable=False)

    # Child reference
    google_sheets_child_id = db.Column(db.Integer, nullable=False, index=True)

    # Relationships
    care_days = db.relationship(
        "AllocatedCareDay",
        back_populates="care_month_allocation",
        primaryjoin="and_(MonthAllocation.id==AllocatedCareDay.care_month_allocation_id, "
        "AllocatedCareDay.deleted_at.is_(None))",
        overlaps="all_care_days"
    )

    # Include soft-deleted care days for admin purposes
    all_care_days = db.relationship(
        "AllocatedCareDay", back_populates="month_allocation_with_deleted", overlaps="care_days,care_month_allocation"
    )

    __table_args__ = (
        db.UniqueConstraint(
            "google_sheets_child_id", "date", name="unique_child_month"
        ),
    )

    @property
    def over_allocation(self):
        """Check if allocated care days exceed the monthly allocation"""
        return self.used_cents > self.allocation_cents

    @property
    def used_days(self):
        """Calculate total days used from active care days"""
        return sum(day.day_count for day in self.care_days)

    @property
    def used_cents(self):
        """Calculate total cents used from active care days"""
        return sum(day.amount_cents for day in self.care_days)

    @property
    def remaining_cents(self):
        """Calculate remaining cents available"""
        return self.allocation_cents - self.used_cents

    def can_add_care_day(self, day_type: CareDayType, provider_id: int) -> bool:
        """Check if we can add a care day of given type without over-allocating"""
        cents_amount = get_care_day_cost(
            day_type, provider_id=provider_id, child_id=self.google_sheets_child_id
        )
        print(
            f"Checking if can add care day of type '{day_type}' costing {cents_amount} cents"
        )
        print(
            f"Current used cents: {self.used_cents}, Allocation cents: {self.allocation_cents}"
        )
        return self.used_cents + cents_amount <= self.allocation_cents

    @staticmethod
    def get_or_create_for_month(child_id: int, month_date: date):
        """Get existing allocation or create with default values"""
        # Normalize to first of month
        month_start = month_date.replace(day=1)

        # Prevent creating allocations for past months
        today = datetime.now().date()
        if month_start < today.replace(day=1):
            raise ValueError(f"Cannot create allocation for a past month. {today} vs {month_start}")

        # Prevent creating allocations for future months too far in advance
        if month_start > today + timedelta(days=31):
            raise ValueError(f"Cannot create allocation for a month that is more than 14 days away.")

        allocation = MonthAllocation.query.filter_by(
            google_sheets_child_id=child_id, date=month_start
        ).first()

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

    @property
    def locked_until_date(self) -> date:
        """Returns the last date (inclusive) for which a newly created care day would be immediately locked."""
        today = date.today()
        # Calculate the Monday of the current week
        current_monday = today - timedelta(days=today.weekday())
        # Calculate the end of day for the current Monday
        current_monday_eod = datetime.combine(current_monday, dt_time(23, 59, 59))

        if datetime.now() > current_monday_eod:
            # If current time is past Monday EOD, all days in current week are locked
            return current_monday + timedelta(days=6) # Sunday of current week
        else:
            # If current time is not yet past Monday EOD, days up to previous Sunday are locked
            return current_monday - timedelta(days=1) # Sunday of previous week

    def __repr__(self):
        return f"<MonthAllocation Child:{self.google_sheets_child_id} {self.date.strftime('%Y-%m')}"
