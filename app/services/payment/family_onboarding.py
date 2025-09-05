"""
Family-specific onboarding implementation.
"""

import uuid
from typing import Optional

from app.exceptions import FamilyNotFoundException
from app.models import FamilyPaymentSettings
from app.services.payment.base_onboarding import BaseOnboarding
from app.supabase.helpers import cols, unwrap_or_error
from app.supabase.tables import Family, Guardian


class FamilyOnboarding(BaseOnboarding):
    """Family-specific onboarding implementation."""

    def get_entity_type_name(self) -> str:
        return "family"

    def get_existing_settings(self, external_id: str) -> Optional[FamilyPaymentSettings]:
        return FamilyPaymentSettings.query.filter_by(family_external_id=external_id).first()

    def get_entity_data(self, external_id: str) -> dict:
        family_results = Family.select_by_id(
            cols(
                Family.ID,
                Guardian.join(
                    Guardian.IS_PRIMARY,
                    Guardian.FIRST_NAME,
                    Guardian.LAST_NAME,
                    Guardian.EMAIL,
                    Guardian.PHONE_NUMBER,
                    Guardian.ADDRESS_1,
                    Guardian.ADDRESS_2,
                    Guardian.CITY,
                    Guardian.STATE,
                    Guardian.ZIP,
                ),
            ),
            int(external_id),
        ).execute()
        family = unwrap_or_error(family_results)

        if family is None:
            raise FamilyNotFoundException(f"Family {external_id} not found")

        return family

    def extract_entity_fields(self, entity_data: dict) -> dict:
        guardian = Guardian.get_primary_guardian(Guardian.unwrap(entity_data))

        return {
            "email": Guardian.EMAIL(guardian),
            "phone_raw": Guardian.PHONE_NUMBER(guardian),
            "first_name": Guardian.FIRST_NAME(guardian),
            "last_name": Guardian.LAST_NAME(guardian),
            "address_line1": Guardian.ADDRESS_1(guardian),
            "address_line2": Guardian.ADDRESS_2(guardian),
            "city": Guardian.CITY(guardian),
            "state": Guardian.STATE(guardian),
            "zip_code": Guardian.ZIP(guardian),
            "country_code": "US",
        }

    def create_payment_settings(self, external_id: str, chek_user_id: str, balance: int) -> FamilyPaymentSettings:
        return FamilyPaymentSettings(
            id=uuid.uuid4(),
            family_external_id=external_id,
            chek_user_id=chek_user_id,
            chek_wallet_balance=balance,
        )

    def get_chek_status(self, chek_user_id: int) -> dict:
        return self.chek_service.get_family_chek_status(chek_user_id)

    def update_settings_from_status(self, settings: FamilyPaymentSettings, status: dict) -> None:
        settings.chek_wallet_balance = status.get("wallet_balance", settings.chek_wallet_balance)
