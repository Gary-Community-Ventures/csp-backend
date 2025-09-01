from typing import Optional

from ..extensions import db
from .mixins import TimestampMixin


class PaymentRate(db.Model, TimestampMixin):
    """Payment rate for a given provider for a specific child"""

    id = db.Column(db.Integer, primary_key=True)

    google_sheets_provider_id = db.Column(db.String(64), nullable=False, index=True)
    google_sheets_child_id = db.Column(db.String(64), nullable=False, index=True)

    half_day_rate_cents = db.Column(db.Integer, nullable=False)
    full_day_rate_cents = db.Column(db.Integer, nullable=False)

    __table_args__ = (
        # Prevent duplicate rates for same provider/child
        db.UniqueConstraint(
            "google_sheets_provider_id",
            "google_sheets_child_id",
            name="unique_provider_child_rate",
        ),
    )

    @staticmethod
    def get(provider_id: str, child_id: str) -> Optional["PaymentRate"]:
        """Get existing rate or create a new one"""
        rate = PaymentRate.query.filter_by(
            google_sheets_provider_id=provider_id, google_sheets_child_id=child_id
        ).first()

        if rate:
            return rate
        else:
            return None

    @staticmethod
    def create(provider_id: str, child_id: str, half_day_rate: int, full_day_rate: int):
        """Create a new payment rate"""
        rate = PaymentRate(
            google_sheets_provider_id=provider_id,
            google_sheets_child_id=child_id,
            half_day_rate_cents=half_day_rate,
            full_day_rate_cents=full_day_rate,
        )
        return rate

    def __repr__(self):
        return (
            f"<PaymentRate {self.id} - Provider {self.google_sheets_provider_id}, Child {self.google_sheets_child_id}>"
        )
