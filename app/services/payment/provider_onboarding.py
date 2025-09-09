"""
Provider-specific onboarding implementation.
"""

import uuid
from typing import Optional

from app.exceptions import ProviderNotFoundException
from app.models import ProviderPaymentSettings
from app.services.payment.base_onboarding import BaseOnboarding
from app.supabase.helpers import cols, unwrap_or_error
from app.supabase.tables import Provider


class ProviderOnboarding(BaseOnboarding):
    """Provider-specific onboarding implementation."""

    def get_entity_type_name(self) -> str:
        return "provider"

    def get_existing_settings(self, provider_id: str) -> Optional[ProviderPaymentSettings]:
        return ProviderPaymentSettings.query.filter_by(provider_supabase_id=provider_id).first()

    def get_entity_data(self, provider_id: str) -> dict:
        provider_result = Provider.select_by_id(
            cols(
                Provider.ID,
                Provider.EMAIL,
                Provider.PHONE_NUMBER,
                Provider.FIRST_NAME,
                Provider.LAST_NAME,
                Provider.ADDRESS_1,
                Provider.ADDRESS_2,
                Provider.CITY,
                Provider.STATE,
                Provider.ZIP,
            ),
            int(provider_id),
        ).execute()
        provider = unwrap_or_error(provider_result)

        if provider is None:
            raise ProviderNotFoundException(f"Provider {provider_id} not found")

        return provider

    def extract_entity_fields(self, entity_data: dict) -> dict:
        return {
            "email": Provider.EMAIL(entity_data),
            "phone_raw": Provider.PHONE_NUMBER(entity_data),
            "first_name": Provider.FIRST_NAME(entity_data),
            "last_name": Provider.LAST_NAME(entity_data),
            "address_line1": Provider.ADDRESS_1(entity_data),
            "address_line2": Provider.ADDRESS_2(entity_data),
            "city": Provider.CITY(entity_data),
            "state": Provider.STATE(entity_data),
            "zip_code": Provider.ZIP(entity_data),
            "country_code": "US",
        }

    def create_payment_settings(self, provider_id: str, chek_user_id: str, balance: int) -> ProviderPaymentSettings:
        return ProviderPaymentSettings(
            id=uuid.uuid4(),
            provider_supabase_id=provider_id,
            chek_user_id=chek_user_id,
            payment_method=None,  # Provider chooses this later
            chek_wallet_balance=balance,
        )

    def get_chek_status(self, chek_user_id: int) -> dict:
        return self.chek_service.get_provider_chek_status(chek_user_id)

    def update_settings_from_status(self, settings: ProviderPaymentSettings, status: dict) -> None:
        settings.chek_direct_pay_id = status.get("direct_pay_id")
        settings.chek_direct_pay_status = status.get("direct_pay_status")
        settings.chek_card_id = status.get("card_id")
        settings.chek_card_status = status.get("card_status")
        settings.chek_wallet_balance = status.get("wallet_balance", settings.chek_wallet_balance)
