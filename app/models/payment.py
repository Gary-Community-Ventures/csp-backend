import uuid

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.schema import ForeignKey

from ..enums.payment_method import PaymentMethod
from ..extensions import db
from .mixins import TimestampMixin


class Payment(db.Model, TimestampMixin):
    id = db.Column(UUID(as_uuid=True), index=True, primary_key=True, default=uuid.uuid4)

    # Link to PaymentIntent (required - payment fulfills an intent)
    payment_intent_id = db.Column(
        UUID(as_uuid=True), ForeignKey("payment_intent.id", name="fk_payment_intent_id"), nullable=False, unique=True
    )
    intent = relationship("PaymentIntent", back_populates="payment")

    # Link to the successful attempt
    successful_attempt_id = db.Column(
        UUID(as_uuid=True), ForeignKey("payment_attempt.id", name="fk_payment_successful_attempt_id"), nullable=False
    )
    successful_attempt = relationship("PaymentAttempt", foreign_keys=[successful_attempt_id])

    external_provider_id = db.Column(db.String(64), nullable=False, index=True)  # Google Sheets ID
    external_child_id = db.Column(db.String(64), nullable=True, index=True)  # Google Sheets ID

    provider_payment_settings_id = db.Column(
        UUID(as_uuid=True),
        ForeignKey("provider_payment_settings.id", name="fk_payment_provider_settings_id"),
        nullable=False,
    )
    provider_payment_settings = relationship("ProviderPaymentSettings", backref="payments")

    chek_user_id = db.Column(db.String(64), nullable=True, index=True)
    chek_direct_pay_id = db.Column(db.String(64), nullable=True, index=True)
    chek_card_id = db.Column(db.String(64), nullable=True, index=True)
    chek_transfer_id = db.Column(db.String(64), nullable=True, index=True)  # ID from Chek for the transfer

    amount_cents = db.Column(db.Integer, nullable=False)
    payment_method = db.Column(db.Enum(PaymentMethod), nullable=False)

    # Relationships
    attempts = relationship("PaymentAttempt", foreign_keys="PaymentAttempt.payment_id", back_populates="payment")

    # Relationships to allocations
    month_allocation_id = db.Column(
        db.Integer, ForeignKey("month_allocation.id", name="fk_payment_month_allocation_id"), nullable=True
    )
    month_allocation = relationship("MonthAllocation", backref="payments")
    allocated_care_days = db.relationship("AllocatedCareDay", back_populates="payment")
    allocated_lump_sums = relationship("AllocatedLumpSum", backref="payment")

    @property
    def has_successful_attempt(self):
        """Check if this payment has at least one successful attempt"""
        return any(attempt.is_successful for attempt in self.attempts)

    @property
    def has_failed_attempt(self):
        """Check if this payment has at least one failed attempt"""
        return any(attempt.is_failed for attempt in self.attempts)

    @property
    def status(self):
        """Compute payment status from attempts"""
        if not self.attempts:
            return "pending"

        latest = max(self.attempts, key=lambda a: a.attempt_number)
        if latest.is_successful:
            return "successful"
        elif latest.status == "wallet_funded":
            return "partially_paid"
        elif all(attempt.status == "failed" for attempt in self.attempts):
            return "failed"
        else:
            return "processing"

    def __repr__(self):
        return f"<Payment {self.id} - Amount: {self.amount_cents} cents - Provider: {self.external_provider_id}>"
