from typing import Optional
from flask import current_app

from app.extensions import db
from app.models.provider import Provider

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

    def create_direct_pay_account_invite(self, invite_request: DirectPayAccountInviteRequest) -> str:
        """
        Sends an invitation to a user to set up a direct pay account.
        """
        invite_data_dict = invite_request.model_dump()
        # The API for this endpoint expects just the user_id in the body, not a nested object
        invite_response_text = self.client.create_direct_pay_account_invite(invite_data_dict["user_id"])
        return invite_response_text

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
                program_id="platform_funds",  # Assuming 'platform_funds' is the correct ID
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

    def refresh_provider_status(self, provider: Provider):
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
