from sqlalchemy.orm import Query
from datetime import datetime, timedelta
from flask import current_app

from ..extensions import db
from .mixins import TimestampMixin
from ..enums.payment_method import PaymentMethod


class Provider(db.Model, TimestampMixin):
    id = db.Column(db.UUID(as_uuid=True), index=True, primary_key=True)
    provider_external_id = db.Column(db.String(64), nullable=True, index=True)

    # Payment-related fields
    chek_user_id = db.Column(db.String(64), nullable=True, index=True)
    chek_direct_pay_id = db.Column(db.String(64), nullable=True, index=True)
    chek_direct_pay_status = db.Column(db.String(32), nullable=True) # Cached status
    chek_card_id = db.Column(db.String(64), nullable=True, index=True)
    chek_card_status = db.Column(db.String(32), nullable=True) # Cached status
    payment_method = db.Column(db.Enum(PaymentMethod), nullable=True)
    last_chek_sync_at = db.Column(db.DateTime, nullable=True) # Timestamp of last sync

    @property
    def payable(self):
        # Check if status is stale
        stale_threshold = timedelta(minutes=5) # Example: 5 minutes
        is_stale = self.last_chek_sync_at is None or \
                   (datetime.utcnow() - self.last_chek_sync_at) > stale_threshold

        if is_stale:
            # Trigger an asynchronous refresh.
            # This would typically involve a background task queue (e.g., Celery, RQ).
            # For now, we just log a warning. The explicit refresh for payment will handle blocking.
            current_app.logger.warning(f"Provider {self.id} Chek status is stale. Consider refreshing.")
            # In a real app, you'd enqueue a task here:
            # current_app.job_manager.enqueue(refresh_chek_status_task, provider_id=self.id)

        # Return payable status based on cached data
        return (self.chek_direct_pay_status == "Active" and self.payment_method == PaymentMethod.ACH) or \
               (self.chek_card_status == "Active" and self.payment_method == PaymentMethod.VIRTUAL_CARD)

    def __repr__(self):
        return f"<Provider {self.id} - External ID: {self.provider_external_id}>"

    @staticmethod
    def new(provider_external_id: str):
        return Provider(provider_external_id=provider_external_id)

    @classmethod
    def provider_by_external_id(cls, id: str) -> Query:
        return cls.query.filter_by(provider_external_id=id)

    @classmethod
    def provider_by_chek_user_id(cls, id: str) -> Query:
        return cls.query.filter_by(chek_user_id=id)

