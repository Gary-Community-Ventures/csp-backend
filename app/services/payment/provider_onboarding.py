"""
Provider-specific onboarding implementation.
"""

import uuid
from typing import Dict, Optional

from app.exceptions import ProviderNotFoundException
from app.models import ProviderPaymentSettings
from app.services.payment.base_onboarding import BaseOnboarding
from app.sheets.mappings import ProviderColumnNames, get_provider, get_providers


class ProviderOnboarding(BaseOnboarding):
    """Provider-specific onboarding implementation."""

    def get_entity_type_name(self) -> str:
        return "provider"

    def get_existing_settings(self, external_id: str) -> Optional[ProviderPaymentSettings]:
        return ProviderPaymentSettings.query.filter_by(provider_external_id=external_id).first()

    def get_entity_data_from_sheets(self, external_id: str) -> Dict:
        provider_rows = get_providers()
        provider_data = get_provider(external_id, provider_rows)

        if not provider_data:
            raise ProviderNotFoundException(f"Provider {external_id} not found in Google Sheets")

        return provider_data

    def extract_entity_fields(self, entity_data: Dict) -> Dict:
        return {
            "email": entity_data.get(ProviderColumnNames.EMAIL),
            "phone_raw": entity_data.get(ProviderColumnNames.PHONE_NUMBER),
            "first_name": entity_data.get(ProviderColumnNames.FIRST_NAME),
            "last_name": entity_data.get(ProviderColumnNames.LAST_NAME),
            "address_line1": entity_data.get(ProviderColumnNames.ADDRESS_LINE_1),
            "address_line2": entity_data.get(ProviderColumnNames.ADDRESS_LINE_2),
            "city": entity_data.get(ProviderColumnNames.CITY),
            "state": entity_data.get(ProviderColumnNames.STATE),
            "zip_code": entity_data.get(ProviderColumnNames.ZIP_CODE),
            "country_code": entity_data.get(ProviderColumnNames.COUNTRY_CODE),
        }

    def create_payment_settings(self, external_id: str, chek_user_id: str, balance: int) -> ProviderPaymentSettings:
        return ProviderPaymentSettings(
            id=uuid.uuid4(),
            provider_external_id=external_id,
            chek_user_id=chek_user_id,
            payment_method=None,  # Provider chooses this later
            chek_wallet_balance=balance,
        )

    def get_chek_status(self, chek_user_id: int) -> Dict:
        return self.chek_service.get_provider_chek_status(chek_user_id)

    def update_settings_from_status(self, settings: ProviderPaymentSettings, status: Dict) -> None:
        settings.chek_direct_pay_id = status.get("direct_pay_id")
        settings.chek_direct_pay_status = status.get("direct_pay_status")
        settings.chek_card_id = status.get("card_id")
        settings.chek_card_status = status.get("card_status")
        settings.chek_wallet_balance = status.get("wallet_balance", settings.chek_wallet_balance)
