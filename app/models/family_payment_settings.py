import uuid
from datetime import datetime, timedelta, timezone

from flask import current_app
from sqlalchemy.orm import Query

from ..config import PROVIDER_STATUS_STALE_MINUTES
from ..extensions import db
from .mixins import TimestampMixin


class FamilyPaymentSettings(db.Model, TimestampMixin):
    __tablename__ = "family_payment_settings"
    id = db.Column(db.UUID(as_uuid=True), index=True, primary_key=True, default=uuid.uuid4)
    family_external_id = db.Column(db.String(64), nullable=True, index=True)

    # Payment-related fields
    chek_user_id = db.Column(db.String(64), nullable=True, index=True)
    chek_wallet_balance = db.Column(db.Integer, nullable=True)  # Cached wallet balance
    last_chek_sync_at = db.Column(db.DateTime(timezone=True), nullable=True)  # Timestamp of last sync

    def is_status_stale(self) -> bool:
        """Check if the family's Chek status information is stale."""
        stale_threshold = timedelta(minutes=PROVIDER_STATUS_STALE_MINUTES)
        return self.last_chek_sync_at is None or (datetime.now(timezone.utc) - self.last_chek_sync_at) > stale_threshold

    @property
    def is_onboarded(self):
        # Check if status is stale and trigger background refresh
        if self.is_status_stale():
            try:
                # Import here to avoid circular imports
                from app.jobs.refresh_family_status_job import (
                    enqueue_family_status_refresh,
                )

                current_app.logger.info(f"Family {self.id} Chek status is stale. Enqueuing background refresh.")
                enqueue_family_status_refresh(self, from_info="is_onboarded_stale_check")
            except Exception as e:
                # Don't fail the property if job enqueue fails
                current_app.logger.error(f"Failed to enqueue status refresh for family {self.id}: {e}")

        return self.chek_user_id is not None
    

    def __repr__(self):
        return f"<FamilyPaymentSettings {self.id} - External ID: {self.family_external_id}>"

    @staticmethod
    def new(family_external_id: str):
        return FamilyPaymentSettings(id=uuid.uuid4(), family_external_id=family_external_id)

    @classmethod
    def by_external_id(cls, id: str) -> Query:
        return cls.query.filter_by(family_external_id=id)

    @classmethod
    def by_chek_user_id(cls, id: str) -> Query:
        return cls.query.filter_by(chek_user_id=id)
