from ..extensions import db
from .mixins import TimestampMixin
from datetime import date

from .allocated_care_day import AllocatedCareDay
from .month_allocation import MonthAllocation


class PaymentRequest(db.Model, TimestampMixin):
    """Payment request for a batch of care days"""

    id = db.Column(db.Integer, primary_key=True)

    # Provider and child info
    google_sheets_provider_id = db.Column(db.Integer, nullable=False, index=True)
    google_sheets_child_id = db.Column(db.Integer, nullable=False, index=True)

    # Derived fields for snapshot of moment
    care_days_count = db.Column(db.Integer, nullable=False)
    amount_in_cents = db.Column(db.Integer, nullable=False)

    # Care days included in this payment (JSON list of IDs)
    care_day_ids = db.Column(db.JSON, nullable=True)

    @property
    def care_days(self):
        """Get the actual AllocatedCareDay objects"""
        if not self.care_day_ids:
            return []
        return AllocatedCareDay.query.filter(
            AllocatedCareDay.id.in_(self.care_day_ids)
        ).all()

    @staticmethod
    def create_for_locked_days(provider_id: int, child_id: int, locked_date: date):
        """Create payment request for all locked, unpaid care days"""
        # Find all care days that are locked and haven't been paid
        care_days = (
            db.session.query(AllocatedCareDay)
            .join(MonthAllocation)
            .filter(
                AllocatedCareDay.provider_google_sheets_id == provider_id,
                MonthAllocation.google_sheets_child_id == child_id,
                AllocatedCareDay.date < locked_date,
                AllocatedCareDay.payment_distribution_requested == False,
                AllocatedCareDay.deleted_at.is_(None),
            )
            .all()
        )

        if not care_days:
            return None

        # Create payment request
        payment_request = PaymentRequest(
            care_day_ids=[day.id for day in care_days],
            care_days_count=len(care_days),
            amount=sum(day.amount_cents for day in care_days),
            provider_google_sheets_id=provider_id,
            child_google_sheets_id=child_id,
        )

        # Mark care days as payment requested
        for day in care_days:
            day.payment_distribution_requested = True

        db.session.add(payment_request)
        db.session.commit()

        return payment_request

    def __repr__(self):
        return f"<PaymentRequest ${self.amount_in_cents / 100:.2f} - Provider {self.google_sheets_provider_id}>"
