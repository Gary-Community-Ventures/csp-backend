from ..extensions import db
from .mixins import TimestampMixin
from datetime import date

from .allocated_care_day import AllocatedCareDay
from .month_allocation import MonthAllocation


class PaymentRequest(db.Model, TimestampMixin):
    """Payment request for a batch of care days"""

    id = db.Column(db.Integer, primary_key=True)

    # Provider and child info
    google_sheets_provider_id = db.Column(db.String(64), nullable=False, index=True)
    google_sheets_child_id = db.Column(db.String(64), nullable=False, index=True)

    # Derived fields for snapshot of moment
    care_days_count = db.Column(db.Integer, nullable=True, default=0)
    amount_in_cents = db.Column(db.Integer, nullable=False)

    # Care days included in this payment (JSON list of IDs)
    care_day_ids = db.Column(db.JSON, nullable=True)

    @property
    def care_days(self):
        """Get the actual AllocatedCareDay objects"""
        if not self.care_day_ids:
            return []
        return AllocatedCareDay.query.filter(AllocatedCareDay.id.in_(self.care_day_ids)).all()

    def __repr__(self):
        return f"<PaymentRequest ${self.amount_in_cents / 100:.2f} - Provider {self.google_sheets_provider_id}>"
