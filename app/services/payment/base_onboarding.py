"""
Base class for onboarding providers and families to Chek payment system.
"""

from abc import ABC, abstractmethod
from typing import Optional, Union

import sentry_sdk
from flask import current_app

from app.exceptions import DataNotFoundException
from app.extensions import db
from app.integrations.chek.schemas import Address, UserCreateRequest
from app.models import FamilyPaymentSettings, ProviderPaymentSettings
from app.services.payment.utils import format_phone_to_e164


class BaseOnboarding(ABC):
    """Abstract base class for onboarding entities to the payment system."""

    def __init__(self, chek_service):
        self.chek_service = chek_service

    @abstractmethod
    def get_entity_type_name(self) -> str:
        """Return the entity type name (e.g., 'provider' or 'family')."""
        pass

    @abstractmethod
    def get_existing_settings(
        self, external_id: str
    ) -> Optional[Union[ProviderPaymentSettings, FamilyPaymentSettings]]:
        """Check if payment settings already exist for this entity."""
        pass

    @abstractmethod
    def get_entity_data(self, external_id: str) -> dict:
        """Get entity data."""
        pass

    @abstractmethod
    def extract_entity_fields(self, entity_data: dict) -> dict:
        """Extract required fields from entity data."""
        pass

    @abstractmethod
    def create_payment_settings(
        self, external_id: str, chek_user_id: str, balance: int
    ) -> Union[ProviderPaymentSettings, FamilyPaymentSettings]:
        """Create and return the payment settings record."""
        pass

    @abstractmethod
    def get_chek_status(self, chek_user_id: int) -> dict:
        """Get the current Chek status for the entity."""
        pass

    @abstractmethod
    def update_settings_from_status(
        self, settings: Union[ProviderPaymentSettings, FamilyPaymentSettings], status: dict
    ) -> None:
        """Update payment settings from Chek status."""
        pass

    def onboard(self, external_id: str) -> Union[ProviderPaymentSettings, FamilyPaymentSettings]:
        """
        Generic onboarding flow for any entity.

        Args:
            external_id: External ID

        Returns:
            Payment settings record for the entity
        """
        entity_type = self.get_entity_type_name()

        try:
            # Check if entity already exists
            existing_settings = self.get_existing_settings(external_id)
            if existing_settings:
                current_app.logger.info(
                    f"{entity_type.capitalize()} {external_id} already exists with Chek user {existing_settings.chek_user_id}"
                )
                return existing_settings

            entity_data = self.get_entity_data(external_id)

            # Extract fields
            fields = self.extract_entity_fields(entity_data)

            # Validate required fields
            if not fields["email"]:
                raise DataNotFoundException(f"{entity_type.capitalize()} {external_id} has no email")

            # Format phone number
            phone = format_phone_to_e164(fields.get("phone_raw"))
            if not phone:
                raise DataNotFoundException(
                    f"{entity_type.capitalize()} {external_id} has invalid phone number: {fields.get('phone_raw')}"
                )

            # Check if Chek user already exists
            existing_chek_user = self.chek_service.get_user_by_email(fields["email"])
            balance = existing_chek_user.balance if existing_chek_user else 0

            if existing_chek_user:
                current_app.logger.info(
                    f"Chek user already exists for email {fields['email']}, linking to {entity_type} {external_id}"
                )
                chek_user_id = str(existing_chek_user.id)
            else:
                # Create new Chek user
                user_request = UserCreateRequest(
                    email=fields["email"],
                    phone=phone,
                    first_name=fields.get("first_name", ""),
                    last_name=fields.get("last_name", ""),
                    address=Address(
                        line1=fields.get("address_line1", ""),
                        line2=fields.get("address_line2", ""),
                        city=fields.get("city", ""),
                        state=fields.get("state", ""),
                        postal_code=fields.get("zip_code", ""),
                        country_code=fields.get("country_code", "US"),
                    ),
                )

                chek_user_response = self.chek_service.create_user(user_request)
                current_app.logger.info(f"Created Chek user {chek_user_response.id} for {entity_type} {external_id}")
                chek_user_id = str(chek_user_response.id)
                balance = chek_user_response.balance

            # Create payment settings record
            payment_settings = self.create_payment_settings(external_id, chek_user_id, balance)
            db.session.add(payment_settings)
            db.session.commit()

            current_app.logger.info(f"Successfully onboarded {entity_type} {external_id} with Chek user {chek_user_id}")
            return payment_settings

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Failed to onboard {entity_type} {external_id}: {e}")
            sentry_sdk.capture_exception(e)
            raise

    def refresh_settings(self, settings: Union[ProviderPaymentSettings, FamilyPaymentSettings]) -> None:
        """
        Generic refresh flow for any entity's payment settings.

        Args:
            settings: Payment settings to refresh
        """
        entity_type = self.get_entity_type_name()

        if not settings.chek_user_id:
            current_app.logger.warning(
                f"{entity_type.capitalize()} {settings.id} has no chek_user_id. Cannot refresh status."
            )
            return

        try:
            # Get status from Chek API
            status = self.get_chek_status(int(settings.chek_user_id))

            # Update settings with new status
            self.update_settings_from_status(settings, status)
            settings.last_chek_sync_at = status.get("timestamp")

            db.session.add(settings)
            db.session.commit()
            current_app.logger.info(f"{entity_type.capitalize()} {settings.id} Chek status refreshed successfully.")

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Failed to refresh Chek status for {entity_type} {settings.id}: {e}")
            sentry_sdk.capture_exception(e)
