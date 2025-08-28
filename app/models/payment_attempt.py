import uuid

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.schema import ForeignKey

from ..enums.payment_method import PaymentMethod
from ..extensions import db
from .mixins import TimestampMixin


class PaymentAttempt(db.Model, TimestampMixin):
    id = db.Column(UUID(as_uuid=True), index=True, primary_key=True, default=uuid.uuid4)

    # Link to PaymentIntent (required - every attempt is for an intent)
    payment_intent_id = db.Column(
        UUID(as_uuid=True), ForeignKey("payment_intent.id", name="fk_payment_attempt_intent_id"), nullable=False
    )
    intent = relationship("PaymentIntent", back_populates="attempts")

    # Payment link - only set when this attempt succeeds and Payment is created
    payment_id = db.Column(
        UUID(as_uuid=True), ForeignKey("payment.id", name="fk_payment_attempt_payment_id"), nullable=True
    )
    payment = relationship("Payment", foreign_keys=[payment_id], back_populates="attempts")

    # Attempt details
    attempt_number = db.Column(db.Integer, nullable=False)  # Sequential within the intent
    payment_method = db.Column(db.Enum(PaymentMethod), nullable=False)  # Method used for this specific attempt

    # Track what actually happened (facts, not status)
    wallet_transfer_id = db.Column(
        db.String(64), nullable=True, index=True
    )  # Chek transfer ID if wallet funding succeeded
    wallet_transfer_at = db.Column(db.DateTime(timezone=True), nullable=True)  # When wallet was funded
    ach_payment_id = db.Column(db.String(64), nullable=True, index=True)  # ACH payment ID if ACH succeeded
    ach_payment_at = db.Column(db.DateTime(timezone=True), nullable=True)  # When ACH completed
    error_message = db.Column(db.Text, nullable=True)  # Error if something failed

    @property
    def status(self):
        """Compute status from facts"""
        if self.ach_payment_id:
            return "success"
        elif self.wallet_transfer_id and self.payment_method == PaymentMethod.ACH:
            return "wallet_funded"  # Transfer succeeded, ACH pending
        elif self.wallet_transfer_id and self.payment_method == PaymentMethod.CARD:
            return "success"  # For cards, wallet transfer is the final step
        elif self.error_message:
            return "failed"
        else:
            return "pending"

    @property
    def is_successful(self):
        """Check if this attempt was successful"""
        if self.payment_method == PaymentMethod.CARD:
            return bool(self.wallet_transfer_id)
        else:  # ACH
            return bool(self.ach_payment_id)

    @property
    def is_failed(self):
        """Check if this attempt has failed"""
        return bool(self.error_message)

    @property
    def is_processing(self):
        """Check if this attempt is still processing"""
        # For ACH: wallet funded but ACH not complete
        if self.payment_method == PaymentMethod.ACH:
            return bool(self.wallet_transfer_id) and not bool(self.ach_payment_id) and not bool(self.error_message)
        # For cards: if we started but haven't succeeded or failed
        return not self.is_successful and not self.is_failed

    def __repr__(self):
        return f"<PaymentAttempt {self.id} - Payment: {self.payment_id} - Attempt: {self.attempt_number} - Status: {self.status}>"
