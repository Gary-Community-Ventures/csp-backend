"""
Family-specific onboarding implementation.
"""

import uuid
from typing import Dict, Optional

from app.exceptions import FamilyNotFoundException
from app.models import FamilyPaymentSettings
from app.services.payment.base_onboarding import BaseOnboarding
from app.sheets.mappings import FamilyColumnNames, get_families, get_family


class FamilyOnboarding(BaseOnboarding):
    """Family-specific onboarding implementation."""

    def get_entity_type_name(self) -> str:
        return "family"

    def get_existing_settings(self, external_id: str) -> Optional[FamilyPaymentSettings]:
        return FamilyPaymentSettings.query.filter_by(family_external_id=external_id).first()

    def get_entity_data_from_sheets(self, external_id: str) -> Dict:
        family_rows = get_families()
        family_data = get_family(external_id, family_rows)

        if not family_data:
            raise FamilyNotFoundException(f"Family {external_id} not found in Google Sheets")

        return family_data

    def extract_entity_fields(self, entity_data: Dict) -> Dict:
        return {
            "email": entity_data.get(FamilyColumnNames.EMAIL),
            "phone_raw": entity_data.get(FamilyColumnNames.PHONE_NUMBER),
            "first_name": entity_data.get(FamilyColumnNames.FIRST_NAME),
            "last_name": entity_data.get(FamilyColumnNames.LAST_NAME),
            "address_line1": entity_data.get(FamilyColumnNames.ADDRESS_LINE1),
            "address_line2": entity_data.get(FamilyColumnNames.ADDRESS_LINE2),
            "city": entity_data.get(FamilyColumnNames.CITY),
            "state": entity_data.get(FamilyColumnNames.STATE),
            "zip_code": entity_data.get(FamilyColumnNames.ZIP_CODE),
            "country_code": entity_data.get(FamilyColumnNames.COUNTRY_CODE),
        }

    def create_payment_settings(self, external_id: str, chek_user_id: str, balance: int) -> FamilyPaymentSettings:
        return FamilyPaymentSettings(
            id=uuid.uuid4(),
            family_external_id=external_id,
            chek_user_id=chek_user_id,
            chek_wallet_balance=balance,
        )

    def get_chek_status(self, chek_user_id: int) -> Dict:
        return self.chek_service.get_family_chek_status(chek_user_id)

    def update_settings_from_status(self, settings: FamilyPaymentSettings, status: Dict) -> None:
        settings.chek_wallet_balance = status.get("wallet_balance", settings.chek_wallet_balance)
