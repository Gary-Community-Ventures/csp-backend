import uuid

from sqlalchemy.dialects.postgresql import UUID
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
    intent = db.relationship("PaymentIntent", back_populates="payment")

    # Link to the successful attempt
    successful_attempt_id = db.Column(
        UUID(as_uuid=True), ForeignKey("payment_attempt.id", name="fk_payment_successful_attempt_id"), nullable=False
    )
    successful_attempt = db.relationship("PaymentAttempt", foreign_keys=[successful_attempt_id])

    external_provider_id = db.Column(db.String(64), nullable=False, index=True)  # External ID
    external_child_id = db.Column(db.String(64), nullable=True, index=True)  # External ID

    provider_payment_settings_id = db.Column(
        UUID(as_uuid=True),
        ForeignKey("provider_payment_settings.id", name="fk_payment_provider_settings_id"),
        nullable=False,
    )
    provider_payment_settings = db.relationship("ProviderPaymentSettings", backref="payments")

    family_payment_settings_id = db.Column(
        UUID(as_uuid=True),
        ForeignKey("family_payment_settings.id", name="fk_payment_family_settings_id"),
        nullable=False,
    )
    family_payment_settings = db.relationship("FamilyPaymentSettings", backref="payments")

    amount_cents = db.Column(db.Integer, nullable=False)
    payment_method = db.Column(db.Enum(PaymentMethod), nullable=False)

    # Relationships to allocations
    month_allocation_id = db.Column(
        db.Integer, ForeignKey("month_allocation.id", name="fk_payment_month_allocation_id"), nullable=True
    )
    month_allocation = db.relationship("MonthAllocation", backref="payments")
    allocated_care_days = db.relationship("AllocatedCareDay", back_populates="payment")
    allocated_lump_sums = db.relationship("AllocatedLumpSum", backref="payment")

    @property
    def has_successful_attempt(self):
        """Check if this payment has a successful attempt"""
        # Payment only exists when there's a successful attempt
        return self.successful_attempt is not None

    @property
    def has_failed_attempt(self):
        """Check if this payment has any failed attempts"""
        # Payment only exists after success, check if there were failed attempts before success
        return self.intent.attempts and any(attempt.is_failed for attempt in self.intent.attempts)

    @property
    def status(self):
        """Compute payment status"""
        # Payment only exists when successful
        if self.successful_attempt and self.successful_attempt.is_successful:
            return "successful"
        # This shouldn't happen as Payment is only created on success
        return "unknown"

    @property
    def chek_transfer_id(self):
        """Get the Chek wallet transfer ID from the successful attempt"""
        if self.successful_attempt:
            return self.successful_attempt.wallet_transfer_id
        return None

    @property
    def chek_ach_payment_id(self):
        """Get the Chek ACH payment ID from the successful attempt"""
        if self.successful_attempt:
            return self.successful_attempt.ach_payment_id
        return None

    @property
    def chek_card_transfer_id(self):
        """Get the Chek card transfer ID from the successful attempt"""
        if self.successful_attempt:
            return self.successful_attempt.card_transfer_id
        return None

    @property
    def family_chek_user_id(self):
        """Get the Chek user ID from the successful attempt"""
        if self.successful_attempt:
            return self.successful_attempt.family_chek_user_id
        return None

    @property
    def provider_chek_user_id(self):
        """Get the Chek user ID from the successful attempt"""
        if self.successful_attempt:
            return self.successful_attempt.provider_chek_user_id
        return None

    @property
    def chek_direct_pay_id(self):
        """Get the Chek direct pay ID from the successful attempt"""
        if self.successful_attempt:
            return self.successful_attempt.chek_direct_pay_id
        return None

    @property
    def chek_card_id(self):
        """Get the Chek card ID from the successful attempt"""
        if self.successful_attempt:
            return self.successful_attempt.chek_card_id
        return None

    def __repr__(self):
        return f"<Payment {self.id} - Amount: {self.amount_cents} cents - Provider: {self.external_provider_id}>"
