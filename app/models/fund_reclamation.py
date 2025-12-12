import uuid

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.schema import ForeignKey

from ..extensions import db
from .mixins import TimestampMixin


class FundReclamation(db.Model, TimestampMixin):
    id = db.Column(UUID(as_uuid=True), index=True, primary_key=True, default=uuid.uuid4)

    amount_cents = db.Column(db.Integer, nullable=False)
    chek_transfer_id = db.Column(db.String(64), nullable=True, index=True)
    chek_user_id = db.Column(db.String(64), nullable=True, index=True)

    # Relationships to allocations
    month_allocation_id = db.Column(
        db.Integer, ForeignKey("month_allocation.id", name="fk_payment_month_allocation_id"), nullable=True
    )
    month_allocation = db.relationship("MonthAllocation", backref="reclaimed_funds")

    def __repr__(self):
        return f"<FundReclamation {self.id} - Amount: {self.amount_cents} cents - Chek Transfer ID: {self.chek_transfer_id}>"
