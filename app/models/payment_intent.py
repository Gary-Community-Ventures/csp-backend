import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship

from ..extensions import db
from .mixins import TimestampMixin


class PaymentIntent(db.Model, TimestampMixin):
    """
    Represents the intent to make a payment for specific care days and/or lump sums.
    This captures WHAT we're trying to pay for, while PaymentAttempts capture the HOW.
    """
    __tablename__ = 'payment_intent'
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Who and what we're paying for
    provider_external_id = db.Column(db.String(64), nullable=False, index=True)
    child_external_id = db.Column(db.String(64), nullable=True, index=True)
    month_allocation_id = db.Column(db.Integer, db.ForeignKey("month_allocation.id"), nullable=False)
    month_allocation = relationship("MonthAllocation", backref="payment_intents")
    
    # Amount to pay (computed from care days + lump sums)
    amount_cents = db.Column(db.Integer, nullable=False)
    
    # What items this payment is for (stored as JSON arrays of IDs)
    care_day_ids = db.Column(JSON, nullable=False, default=list)  # List of AllocatedCareDay IDs
    lump_sum_ids = db.Column(JSON, nullable=False, default=list)  # List of AllocatedLumpSum IDs
    
    # Provider payment settings at time of intent creation
    provider_payment_settings_id = db.Column(
        UUID(as_uuid=True), 
        db.ForeignKey("provider_payment_settings.id"), 
        nullable=False
    )
    provider_payment_settings = relationship("ProviderPaymentSettings", backref="payment_intents")
    
    # Relationships
    attempts = relationship("PaymentAttempt", back_populates="intent", order_by="PaymentAttempt.attempt_number")
    payment = relationship("Payment", back_populates="intent", uselist=False)  # One-to-one when successful
    
    # Metadata
    description = db.Column(db.Text, nullable=True)  # Human-readable description
    
    @property
    def is_paid(self) -> bool:
        """Check if this intent has been successfully paid"""
        return self.payment is not None
    
    @property
    def status(self) -> str:
        """Compute status from attempts and payment"""
        if self.payment:
            return "paid"
        elif not self.attempts:
            return "pending"
        elif any(attempt.is_processing for attempt in self.attempts):
            return "processing"
        elif all(attempt.is_failed for attempt in self.attempts):
            return "failed"
        else:
            return "pending"
    
    @property
    def latest_attempt(self) -> Optional["PaymentAttempt"]:
        """Get the most recent attempt"""
        return self.attempts[-1] if self.attempts else None
    
    @property
    def successful_attempt(self) -> Optional["PaymentAttempt"]:
        """Get the successful attempt if any"""
        return next((a for a in self.attempts if a.is_successful), None)
    
    @property
    def can_retry(self) -> bool:
        """Check if this intent can be retried"""
        if self.is_paid:
            return False
        # Could add more logic here (max retries, time limits, etc.)
        return True
    
    def get_care_days(self) -> List["AllocatedCareDay"]:
        """Get the actual AllocatedCareDay objects"""
        from .allocated_care_day import AllocatedCareDay
        if not self.care_day_ids:
            return []
        return AllocatedCareDay.query.filter(AllocatedCareDay.id.in_(self.care_day_ids)).all()
    
    def get_lump_sums(self) -> List["AllocatedLumpSum"]:
        """Get the actual AllocatedLumpSum objects"""
        from .allocated_lump_sum import AllocatedLumpSum
        if not self.lump_sum_ids:
            return []
        return AllocatedLumpSum.query.filter(AllocatedLumpSum.id.in_(self.lump_sum_ids)).all()
    
    @staticmethod
    def find_existing(care_day_ids: List[int], lump_sum_ids: List[int]) -> Optional["PaymentIntent"]:
        """Find an existing unpaid intent for the same items"""
        # This is a bit tricky with JSON columns - might need a custom query
        # For now, return None and always create new (can optimize later)
        return None
    
    def __repr__(self):
        return f"<PaymentIntent {self.id} - {self.provider_external_id} - ${self.amount_cents/100:.2f} - Status: {self.status}>"