import uuid
from datetime import datetime, timedelta, timezone

from flask import current_app
from sqlalchemy.orm import Query

from ..config import PROVIDER_STATUS_STALE_MINUTES
from ..enums.payment_method import PaymentMethod
from ..extensions import db
from .mixins import TimestampMixin


class ProviderPaymentSettings(db.Model, TimestampMixin):
    __tablename__ = "provider_payment_settings"
    id = db.Column(db.UUID(as_uuid=True), index=True, primary_key=True, default=uuid.uuid4)
    provider_external_id = db.Column(db.String(64), nullable=True, index=True)

    # Payment-related fields
    chek_user_id = db.Column(db.String(64), nullable=True, index=True)
    chek_direct_pay_id = db.Column(db.String(64), nullable=True, index=True)
    chek_direct_pay_status = db.Column(db.String(32), nullable=True)  # Cached status
    chek_card_id = db.Column(db.String(64), nullable=True, index=True)
    chek_card_status = db.Column(db.String(32), nullable=True)  # Cached status
    chek_wallet_balance = db.Column(db.Integer, nullable=True)  # Cached wallet balance
    payment_method = db.Column(db.Enum(PaymentMethod), nullable=True)
    payment_method_updated_at = db.Column(
        db.DateTime(timezone=True), nullable=True
    )  # Timestamp of last payment method change
    last_chek_sync_at = db.Column(db.DateTime(timezone=True), nullable=True)  # Timestamp of last sync

    def validate_payment_method_status(self) -> tuple[bool, str]:
        """
        Validate payment method status with detailed error messages.

        Returns:
            tuple: (is_valid, error_message)
        """
        if not self.payment_method:
            return False, "No payment method configured"

        if self.payment_method == PaymentMethod.ACH:
            if not self.chek_direct_pay_id:
                return False, "ACH payment method selected but no direct pay account configured"

            if not self.chek_direct_pay_status:
                return False, "ACH direct pay account has no status information"

            if self.chek_direct_pay_status == "Pending":
                return False, "ACH direct pay account is still pending setup"

            if self.chek_direct_pay_status == "Inactive":
                return False, "ACH direct pay account is inactive"

            if self.chek_direct_pay_status != "Active":
                return False, f"ACH direct pay account has invalid status: {self.chek_direct_pay_status}"

        elif self.payment_method == PaymentMethod.CARD:
            if not self.chek_card_id:
                return False, "Card payment method selected but no virtual card configured"

            if not self.chek_card_status:
                return False, "Virtual card has no status information"

            if self.chek_card_status == "Pending":
                return False, "Virtual card is still pending setup"

            if self.chek_card_status == "Inactive":
                return False, "Virtual card is inactive"

            if self.chek_card_status != "Active":
                return False, f"Virtual card has invalid status: {self.chek_card_status}"

        return True, "Payment method is valid and active"

    def is_status_stale(self) -> bool:
        """Check if the provider's Chek status information is stale."""
        stale_threshold = timedelta(minutes=PROVIDER_STATUS_STALE_MINUTES)
        return self.last_chek_sync_at is None or (datetime.now(timezone.utc) - self.last_chek_sync_at) > stale_threshold

    @property
    def is_payable(self):
        # Check if status is stale and trigger background refresh
        if self.is_status_stale():
            try:
                # Import here to avoid circular imports
                from app.jobs.refresh_provider_settings_job import (
                    enqueue_provider_status_refresh,
                )

                current_app.logger.info(f"Provider {self.id} Chek status is stale. Enqueuing background refresh.")
                enqueue_provider_status_refresh(self, from_info="is_payable_stale_check")
            except Exception as e:
                # Don't fail the property if job enqueue fails
                current_app.logger.warning(f"Failed to enqueue status refresh for provider {self.id}: {e}")

        # Use detailed validation for payable status (with current cached data)
        is_valid, _ = self.validate_payment_method_status()
        current_app.logger.debug(f"Provider {self.id} payment method validation: {is_valid}")
        return is_valid

    def __repr__(self):
        return f"<ProviderPaymentSettings {self.id} - External ID: {self.provider_external_id}>"

    @staticmethod
    def new(provider_external_id: str):
        return ProviderPaymentSettings(id=uuid.uuid4(), provider_external_id=provider_external_id)

    @classmethod
    def provider_by_external_id(cls, id: str) -> Query:
        return cls.query.filter_by(provider_external_id=id)

    @classmethod
    def provider_by_chek_user_id(cls, id: str) -> Query:
        return cls.query.filter_by(chek_user_id=id)
