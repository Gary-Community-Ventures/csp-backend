from datetime import datetime
from typing import Optional
from flask import current_app
import sentry_sdk

from app.extensions import db
from app.models.provider_payment_settings import ProviderPaymentSettings

from .client import ChekClient
from .schemas import (
    ACHFundingSource,
    ACHPaymentRequest,
    ACHPaymentType,
    Address,
    Card,
    CardCreateRequest,
    CardCreateResponse,
    DirectPayAccount,
    DirectPayAccountInviteRequest,
    FlowDirection,
    TransferBalanceRequest,
    TransferBalanceResponse,
    User,
    UserCreateRequest,
    UserCreateResponse,
)


class ChekService:
    """
    A service for interacting with the Chek platform, providing
    higher-level operations than the raw client.
    """

    def __init__(self, app):
        self.client = ChekClient(app.config)
        self.program_id = app.config.get("CHEK_PROGRAM_ID")

    def get_user_by_email(self, email: str) -> Optional[User]:
        """
        Retrieves a user by their email address.

        NOTE: This implementation is based on the user's request to check only
        the first result of the list endpoint, as the API's server-side
        filtering appears to be unreliable.
        """
        # We pass the email parameter optimistically, but don't rely on it.
        users_response = self.client.list_users(email=email)
        results = users_response.get("results")
        print("Chek list_users results:", results)

        if not results:
            return None

        # Check if the first user in the list matches the email.
        first_user_data = results[0]
        if first_user_data.get("email") == email:
            return User.model_validate(first_user_data)

        return None

    def create_user(self, user_request: UserCreateRequest) -> UserCreateResponse:
        """Creates a new user."""
        user_data_dict = user_request.model_dump(exclude_none=True)
        user_json = self.client.create_user(user_data_dict)
        return UserCreateResponse.model_validate(user_json)

    def get_user(self, user_id: int) -> User:
        """Retrieves a specific user by their ID."""
        user_json = self.client.get_user(user_id)
        return User.model_validate(user_json)

    def create_card(self, card_request: CardCreateRequest) -> CardCreateResponse:
        """
        Creates a virtual card for a user.
        """
        card_data_dict = card_request.model_dump(exclude_none=True)
        card_json = self.client.create_card(card_data_dict)
        return CardCreateResponse.model_validate(card_json)

    def get_card(self, card_id: int) -> Card:
        """
        Retrieves details for a specific card.
        """
        card_json = self.client.get_card(card_id)
        return Card.model_validate(card_json)

    def invite_direct_pay_account(self, invite_request: DirectPayAccountInviteRequest) -> DirectPayAccount:
        """
        Sends an invitation to a user to set up a direct pay account.
        Returns the DirectPayAccount object with status 'Invited'.
        """
        invite_data_dict = invite_request.model_dump()
        # The API for this endpoint expects just the user_id in the body
        response_json = self.client.create_direct_pay_account_invite(invite_data_dict["user_id"])
        return DirectPayAccount.model_validate(response_json)

    def get_direct_pay_account(self, account_id: int) -> DirectPayAccount:
        """
        Retrieves details for a specific direct pay account.
        """
        account_json = self.client.get_direct_pay_account(account_id)
        return DirectPayAccount.model_validate(account_json)

    def transfer_balance(
        self, user_id: int, request: TransferBalanceRequest
    ) -> TransferBalanceResponse:
        """
        Transfers funds between a Program and a User Wallet.
        """
        endpoint = f"users/{user_id}/transfer_balance/"
        request_data = request.model_dump()
        response_json = self.client._request("POST", endpoint, json=request_data)
        return TransferBalanceResponse.model_validate(response_json)
    

    def pay_user(self, user_id: int, amount: int) -> bool:
        """
        Pays a user from the platform's funds.
        """
        return self.transfer_balance(
            user_id,
            TransferBalanceRequest(
                flow_direction=FlowDirection.PROGRAM_TO_WALLET,
                program_id=self.program_id,
                amount=amount,
            ),
        )
    

    def send_ach_payment(
        self, direct_pay_account_id: int, request: ACHPaymentRequest
    ) -> DirectPayAccount:
        """
        Initiates a Same-Day ACH transfer to a recipient's linked bank account.
        Requires the DirectPay account to be Active.
        """
        # Pre-check: Get the DirectPayAccount and check its status
        direct_pay_account = self.get_direct_pay_account(direct_pay_account_id)
        if direct_pay_account.status != "Active":
            raise ValueError(
                f"DirectPay account {direct_pay_account_id} is not Active. Current status: {direct_pay_account.status}"
            )

        endpoint = f"directpay_accounts/{direct_pay_account_id}/send_payment/"
        request_data = request.model_dump()
        response_json = self.client._request("POST", endpoint, json=request_data)
        return DirectPayAccount.model_validate(response_json)

    def refresh_provider_status(self, provider: ProviderPaymentSettings):
        """
        Refreshes the Chek status of a provider from the Chek API and updates the database.
        """
        if not provider.chek_user_id:
            current_app.logger.warning(f"Provider {provider.id} has no chek_user_id. Cannot refresh status.")
            return

        try:
            # Fetch user details to get latest direct pay and card info
            user_details = self.get_user(int(provider.chek_user_id))

            # Update direct pay status
            if user_details.directpay:
                provider.chek_direct_pay_id = str(user_details.directpay.id)
                provider.chek_direct_pay_status = user_details.directpay.status
            else:
                provider.chek_direct_pay_id = None
                provider.chek_direct_pay_status = None

            # Update card status (assuming a provider might have one primary card for now)
            if user_details.cards:
                # Assuming the first card in the list is the relevant one for status
                first_card = user_details.cards[0]
                provider.chek_card_id = first_card.id
                provider.chek_card_status = first_card.status
            else:
                provider.chek_card_id = None
                provider.chek_card_status = None

            provider.last_chek_sync_at = datetime.utcnow()
            db.session.add(provider)
            db.session.commit()
            current_app.logger.info(f"Provider {provider.id} Chek status refreshed successfully.")

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Failed to refresh Chek status for provider {provider.id}: {e}")
            sentry_sdk.capture_exception(e)
    
    def onboard_provider(self, provider_external_id: str) -> ProviderPaymentSettings:
        """
        Onboards a new provider by fetching their info from Google Sheets,
        creating a Chek user, and creating a ProviderPaymentSettings record.
        
        Args:
            provider_external_id: The external provider ID from Google Sheets
            
        Returns:
            ProviderPaymentSettings object with Chek user created
        """
        from app.sheets.mappings import get_providers, get_provider, ProviderColumnNames
        
        try:
            # Check if provider already exists
            existing_provider = ProviderPaymentSettings.query.filter_by(
                provider_external_id=provider_external_id
            ).first()
            
            if existing_provider:
                current_app.logger.info(f"Provider {provider_external_id} already exists with Chek user {existing_provider.chek_user_id}")
                return existing_provider
            
            # Get provider data from Google Sheets
            provider_rows = get_providers()
            provider_data = get_provider(provider_external_id, provider_rows)
            
            if not provider_data:
                raise ValueError(f"Provider {provider_external_id} not found in Google Sheets")
            
            # Extract provider information
            provider_email = provider_data.get(ProviderColumnNames.EMAIL)
            first_name = provider_data.get(ProviderColumnNames.FIRST_NAME, "")
            last_name = provider_data.get(ProviderColumnNames.LAST_NAME, "")
            
            # Get address information from Google Sheets
            street_address = provider_data.get(ProviderColumnNames.ADDRESS, "")
            city = provider_data.get(ProviderColumnNames.CITY, "")
            state = provider_data.get(ProviderColumnNames.STATE, "")
            zip_code = provider_data.get(ProviderColumnNames.ZIP, "")
            
            if not provider_email:
                raise ValueError(f"Provider {provider_external_id} has no email in Google Sheets")
            
            # Check if Chek user already exists with this email
            existing_chek_user = self.get_user_by_email(provider_email)
            
            if existing_chek_user:
                # User already exists in Chek, just create the ProviderPaymentSettings
                current_app.logger.info(f"Chek user already exists for email {provider_email}, linking to provider {provider_external_id}")
                
                provider = ProviderPaymentSettings(
                    id=uuid.uuid4(),
                    provider_external_id=provider_external_id,
                    chek_user_id=str(existing_chek_user.id),
                    payment_method=None  # Provider chooses this later
                )
                db.session.add(provider)
                db.session.commit()
                return provider
            
            # Create new Chek user with Google Sheets data
            user_request = UserCreateRequest(
                email=provider_email,
                first_name=first_name,
                last_name=last_name,
                address=Address(
                    line1=street_address or "",
                    city=city or "",
                    state=state or "",
                    postal_code=zip_code or "",
                    country="US"
                )
            )
            
            chek_user_response = self.create_user(user_request)
            current_app.logger.info(f"Created Chek user {chek_user_response.id} for provider {provider_external_id}")
            
            # Create ProviderPaymentSettings with the new Chek user ID
            provider = ProviderPaymentSettings(
                id=uuid.uuid4(),
                provider_external_id=provider_external_id,
                chek_user_id=str(chek_user_response.id),
                payment_method=None  # Provider chooses this later
            )
            db.session.add(provider)
            db.session.commit()
            
            current_app.logger.info(f"Successfully onboarded provider {provider_external_id} with Chek user {chek_user_response.id}")
            return provider
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Failed to onboard provider {provider_external_id}: {e}")
            sentry_sdk.capture_exception(e)
            raise
