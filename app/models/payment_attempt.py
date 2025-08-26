from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.schema import ForeignKey
from sqlalchemy.orm import relationship

from ..extensions import db
from .mixins import TimestampMixin


class PaymentAttempt(db.Model, TimestampMixin):
    id = db.Column(UUID(as_uuid=True), index=True, primary_key=True)
    payment_id = db.Column(UUID(as_uuid=True), ForeignKey('payment.id'), nullable=False)
    payment = relationship('Payment', backref='attempts')

    attempt_number = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(32), nullable=False)  # e.g., 'pending', 'success', 'failed', 'retrying'
    chek_transfer_id = db.Column(db.String(64), nullable=True, index=True) # ID from Chek for this specific attempt
    error_message = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"<PaymentAttempt {self.id} - Payment: {self.payment_id} - Attempt: {self.attempt_number} - Status: {self.status}>"
