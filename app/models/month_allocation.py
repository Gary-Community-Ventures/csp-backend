from ..extensions import db
from .mixins import TimestampMixin
from datetime import datetime, date, timedelta
from typing import List
from decimal import Decimal
from .utils import get_care_day_cost


class MonthAllocation(db.Model, TimestampMixin):
    """Monthly allocation for a child"""

    id = db.Column(db.Integer, primary_key=True)

    # Month/Year as first day of month (e.g., 2024-03-01 for March 2024)
    date = db.Column(db.Date, nullable=False, index=True)

    # Allocation amounts
    allocation_dollars = db.Column(db.Numeric(10, 2), nullable=False)
    allocation_days = db.Column(
        db.Numeric(4, 1), nullable=False
    )  # Allow half days (e.g., 20.5)

    # Child reference
    google_sheets_child_id = db.Column(db.Integer, nullable=False, index=True)

    # Relationships
    care_days = db.relationship(
        "AllocatedCareDay",
        backref="care_month_allocation",
        primaryjoin="and_(MonthAllocation.id==AllocatedCareDay.care_month_allocation_id, "
        "AllocatedCareDay.deleted_at.is_(None))",
    )

    # Include soft-deleted care days for admin purposes
    all_care_days = db.relationship(
        "AllocatedCareDay", backref="month_allocation_with_deleted"
    )

    __table_args__ = (
        db.UniqueConstraint(
            "google_sheets_child_id", "date", name="unique_child_month"
        ),
    )

    @property
    def over_allocation(self):
        """Check if allocated care days exceed the monthly allocation"""
        return (
            self.used_days > self.allocation_days
            or self.used_dollars > self.allocation_dollars
        )

    @property
    def used_days(self):
        """Calculate total days used from active care days"""
        return sum(day.day_count for day in self.care_days)

    @property
    def used_dollars(self):
        """Calculate total dollars used from active care days"""
        return sum(day.amount_dollars for day in self.care_days)

    @property
    def remaining_days(self):
        """Calculate remaining days available"""
        return self.allocation_days - self.used_days

    @property
    def remaining_dollars(self):
        """Calculate remaining dollars available"""
        return self.allocation_dollars - self.used_dollars

    def can_add_care_day(self, day_type: str) -> bool:
        """Check if we can add a care day of given type without over-allocating"""
        day_count = Decimal("1.0") if day_type == "Full Day" else Decimal("0.5")
        dollar_amount = get_care_day_cost(day_type)

        return (
            self.used_days + day_count <= self.allocation_days
            and self.used_dollars + dollar_amount <= self.allocation_dollars
        )

    @staticmethod
    def get_or_create_for_month(child_id: int, month_date: date):
        """Get existing allocation or create with default values"""
        # Normalize to first of month
        month_start = month_date.replace(day=1)

        allocation = MonthAllocation.query.filter_by(
            google_sheets_child_id=child_id, date=month_start
        ).first()

        if not allocation:
            # Create with hardcoded default values
            allocation = MonthAllocation(
                google_sheets_child_id=child_id,
                date=month_start,
                allocation_dollars=1200.00,  # Hardcoded for now
                allocation_days=20.0,  # Hardcoded for now
            )
            db.session.add(allocation)
            db.session.commit()

        return allocation

    def __repr__(self):
        return f"<MonthAllocation Child:{self.google_sheets_child_id} {self.date.strftime('%Y-%m')}"
