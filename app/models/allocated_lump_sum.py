from datetime import datetime

from ..extensions import db
from .mixins import TimestampMixin
from .month_allocation import MonthAllocation


class AllocatedLumpSum(db.Model, TimestampMixin):
    """Allocated lump sum for a care month"""

    id = db.Column(db.Integer, primary_key=True)

    # Relationships
    care_month_allocation_id = db.Column(db.Integer, db.ForeignKey("month_allocation.id"), nullable=False)
    care_month_allocation = db.relationship(
        "MonthAllocation",
        back_populates="lump_sums",
        foreign_keys=[care_month_allocation_id],
    )

    # Calculated fields
    amount_cents = db.Column(db.Integer, nullable=False)

    # Provider info
    provider_google_sheets_id = db.Column(db.String(64), nullable=False, index=True)

    paid_at = db.Column(db.DateTime, nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=True)

    @property
    def is_paid(self) -> bool:
        """Check if this lump sum has been paid."""
        return self.paid_at is not None

    def mark_as_paid(self):
        """Mark this lump sum as paid."""
        self.paid_at = db.func.current_timestamp()

    @staticmethod
    def create_lump_sum(
        allocation: "MonthAllocation",
        provider_id: str,
        amount_cents: int,
    ):
        # Validate inputs
        if not isinstance(allocation, MonthAllocation):
            raise ValueError("Invalid allocation provided")
        if not isinstance(provider_id, str) or not provider_id:
            raise ValueError("Invalid provider ID")
        if not isinstance(amount_cents, int) or amount_cents <= 0:
            raise ValueError("Amount must be a positive integer in cents")

        # Check if allocation can handle this lump sum
        if not allocation.can_add_lump_sum(amount_cents):
            raise ValueError("Adding this lump sum would exceed monthly allocation")

        # Create new lump sum
        lump_sum = AllocatedLumpSum(
            care_month_allocation_id=allocation.id,
            provider_google_sheets_id=provider_id,
            amount_cents=amount_cents,
            submitted_at=datetime.utcnow(),
        )

        db.session.add(lump_sum)
        db.session.commit()
        return lump_sum

    def to_dict(self):
        """Returns a dictionary representation of the AllocatedCareDay."""
        return {
            "id": self.id,
            "care_month_allocation_id": self.care_month_allocation_id,
            "provider_google_sheets_id": self.provider_google_sheets_id,
            "amount_cents": self.amount_cents,
            "paid_at": self.paid_at,
            "submitted_at": self.submitted_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def __repr__(self):
        return f"<AllocatedLumpSum {self.id} - Provider {self.provider_google_sheets_id} Amount {self.amount_cents}>"
