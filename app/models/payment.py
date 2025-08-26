from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.schema import ForeignKey
from sqlalchemy.orm import relationship

from ..extensions import db
from .mixins import TimestampMixin
from ..enums.payment_method import PaymentMethod


class Payment(db.Model, TimestampMixin):
    id = db.Column(UUID(as_uuid=True), index=True, primary_key=True)
    external_provider_id = db.Column(db.String(64), nullable=False, index=True) # Google Sheets ID
    external_child_id = db.Column(db.String(64), nullable=True, index=True) # Google Sheets ID

    provider_settings_id = db.Column(UUID(as_uuid=True), ForeignKey('provider_payment_settings.id'), nullable=False)
    provider_settings = relationship('ProviderPaymentSettings', backref='payments')

    chek_user_id = db.Column(db.String(64), nullable=True, index=True)
    chek_direct_pay_id = db.Column(db.String(64), nullable=True, index=True)
    chek_card_id = db.Column(db.String(64), nullable=True, index=True)
    chek_transfer_id = db.Column(db.String(64), nullable=True, index=True) # ID from Chek for the transfer

    amount_cents = db.Column(db.Integer, nullable=False)
    payment_method = db.Column(db.Enum(PaymentMethod), nullable=False)

    # Relationships to allocations (assuming these are separate models)
    month_allocation_id = db.Column(db.Integer, ForeignKey('month_allocation.id'), nullable=True)
    month_allocation = relationship('MonthAllocation', backref='payments')
    allocated_care_days = db.relationship(
        "AllocatedCareDay", back_populates="payment"
    )
    allocated_lump_sums = relationship('AllocatedLumpSum', backref='payments')

    def __repr__(self):
        return f"<Payment {self.id} - Amount: {self.amount_cents} cents - Provider: {self.provider_id}>"
