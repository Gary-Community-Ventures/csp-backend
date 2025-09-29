from datetime import datetime, timezone

from ..constants import MAX_PAYMENT_AMOUNT_CENTS
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

    amount_cents = db.Column(db.Integer, nullable=False)
    hours = db.Column(db.Float, nullable=True)
    days = db.Column(db.Integer, nullable=True)
    half_days = db.Column(db.Integer, nullable=True)

    # Provider info
    provider_google_sheets_id = db.Column(db.String(64), nullable=True, index=True)
    provider_supabase_id = db.Column(db.String(64), nullable=True, index=True)

    # Payment tracking
    payment_id = db.Column(
        db.UUID(as_uuid=True), db.ForeignKey("payment.id", name="fk_allocated_lump_sum_payment_id"), nullable=True
    )
    paid_at = db.Column(db.DateTime(timezone=True), nullable=True)
    submitted_at = db.Column(db.DateTime(timezone=True), nullable=True)

    @property
    def is_paid(self) -> bool:
        """Check if this lump sum has been paid."""
        return self.paid_at is not None

    def mark_as_paid(self):
        """Mark this lump sum as paid."""
        self.paid_at = datetime.now(timezone.utc)

    @staticmethod
    def create_lump_sum(
        allocation: "MonthAllocation",
        provider_id: str,
        amount_cents: int,
        days: int,
        half_days: int,
    ):
        if not isinstance(amount_cents, int) or amount_cents <= 0:
            raise ValueError("Amount must be a positive integer in cents")

        if not isinstance(days, int) or days < 0:
            raise ValueError("Days must be a non-negative integer")

        if not isinstance(half_days, int) or half_days < 0:
            raise ValueError("Half days must be a non-negative integer")

        if days == 0 and half_days == 0:
            raise ValueError("At least one of days or half_days must be greater than zero")

        # Check if lump sum exceeds maximum payment amount
        if amount_cents > MAX_PAYMENT_AMOUNT_CENTS:
            raise ValueError(
                f"Lump sum amount ${amount_cents / 100:.2f} exceeds maximum allowed payment "
                f"of ${MAX_PAYMENT_AMOUNT_CENTS / 100:.2f}"
            )

        # Check if allocation can handle this lump sum
        if not allocation.can_add_lump_sum(amount_cents):
            raise ValueError("Adding this lump sum would exceed monthly allocation")

        # Create new lump sum
        lump_sum = AllocatedLumpSum(
            care_month_allocation_id=allocation.id,
            provider_supabase_id=provider_id,
            amount_cents=amount_cents,
            submitted_at=datetime.now(timezone.utc),
            days=days,
            half_days=half_days,
        )

        return lump_sum

    def to_dict(self):
        """Returns a dictionary representation of the AllocatedCareDay."""
        return {
            "id": self.id,
            "care_month_allocation_id": self.care_month_allocation_id,
            "provider_supabase_id": self.provider_supabase_id,
            "amount_cents": self.amount_cents,
            "paid_at": self.paid_at,
            "submitted_at": self.submitted_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def __repr__(self):
        return f"<AllocatedLumpSum {self.id} - Provider {self.provider_supabase_id} Amount {self.amount_cents}>"
