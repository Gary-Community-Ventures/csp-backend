from ..extensions import db
from .mixins import TimestampMixin


class PaymentRequest(db.Model, TimestampMixin):
    id = db.Column(db.Integer, primary_key=True)
    google_sheets_provider_id = db.Column(db.Integer, nullable=False)
    google_sheets_child_id = db.Column(db.Integer, nullable=False)
    amount_in_cents = db.Column(db.Integer, nullable=False)
    hours = db.Column(db.Float, nullable=False)
    # Add any other fields that might be useful for tracking the payment request

    def __repr__(self):
        return f"<PaymentRequest {self.id} - Provider: {self.google_sheets_provider_id} - Child: {self.google_sheets_child_id}>"

    @staticmethod
    def new(google_sheets_provider_id: int, google_sheets_child_id: int, amount_in_cents: int, hours: float):
        return PaymentRequest(
            google_sheets_provider_id=google_sheets_provider_id,
            google_sheets_child_id=google_sheets_child_id,
            amount_in_cents=amount_in_cents,
            hours=hours,
        )
