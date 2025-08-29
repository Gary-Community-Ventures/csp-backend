from datetime import datetime, timezone
from typing import Optional

import sentry_sdk
from flask import current_app

from .client import ChekClient
from .schemas import (
    ACHPaymentRequest,
    ACHPaymentResponse,
    Card,
    CardCreateRequest,
    CardCreateResponse,
    DirectPayAccount,
    DirectPayAccountInviteRequest,
    TransferBalanceRequest,
    TransferBalanceResponse,
    TransferFundsToCardRequest,
    TransferFundsToCardResponse,
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
        current_app.logger.debug(f"Chek list_users results: {results}")

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

    def create_card(self, user_id: int, card_request: CardCreateRequest) -> CardCreateResponse:
        """
        Creates a virtual card for a user using the new endpoint.
        """
        card_data_dict = card_request.model_dump(exclude_none=True)
        card_json = self.client.create_card(user_id, card_data_dict)
        current_app.logger.debug(f"Chek create_card response: {card_json}")
        return CardCreateResponse.model_validate(card_json)

    def get_card(self, card_id: int) -> Card:
        """
        Retrieves details for a specific card.
        """
        card_json = self.client.get_card(card_id)
        return Card.model_validate(card_json)

    def invite_direct_pay_account(self, invite_request: DirectPayAccountInviteRequest) -> str:
        """
        Sends an invitation to a user to set up a direct pay account.
        Returns the response message string.
        """
        invite_data_dict = invite_request.model_dump()
        # The API for this endpoint expects just the user_id in the body
        response_json = self.client.create_direct_pay_account_invite(invite_data_dict["user_id"])
        current_app.logger.debug(f"DirectPay account invite response: {response_json}")
        # The API returns a simple string message
        return response_json

    def get_direct_pay_account(self, account_id: str) -> DirectPayAccount:
        """
        Retrieves details for a specific direct pay account.
        """
        account_json = self.client.get_direct_pay_account(account_id)
        return DirectPayAccount.model_validate(account_json)

    def transfer_balance(self, user_id: int, request: TransferBalanceRequest) -> TransferBalanceResponse:
        """
        Transfers funds between a Program and a User Wallet.
        """
        endpoint = f"users/{user_id}/transfer_balance/"
        request_data = request.model_dump()
        response_json = self.client._request("POST", endpoint, json=request_data)
        current_app.logger.debug(f"Chek transfer_balance response: {response_json}")
        return TransferBalanceResponse.model_validate(response_json)

    def send_ach_payment(
        self, user_id: int, direct_pay_account_id: str, request: ACHPaymentRequest
    ) -> ACHPaymentResponse:
        """
        Initiates a Same-Day ACH transfer to a recipient's linked bank account.
        Requires the DirectPay account to be Active.
        """
        endpoint = f"directpay_accounts/{user_id}/send_payment/"
        request_data = request.model_dump()
        response_json = self.client._request("POST", endpoint, json=request_data)
        current_app.logger.debug(f"Chek send_ach_payment response: {response_json}")
        return ACHPaymentResponse.model_validate(response_json)
    
    def transfer_funds_to_card(
        self, card_id: str, request: TransferFundsToCardRequest
    ) -> TransferFundsToCardResponse:
        """
        Transfers funds to or from a virtual card.
        Can allocate funds to a card or remit funds from a card back to wallet.
        """
        endpoint = f"cards/{card_id}/transfer_balance/"
        request_data = request.model_dump()
        response_json = self.client._request("POST", endpoint, json=request_data)
        current_app.logger.debug(f"Chek transfer_funds_to_card response: {response_json}")
        return TransferFundsToCardResponse.model_validate(response_json)

    def get_provider_chek_status(self, chek_user_id: int) -> dict:
        """
        Fetches the current Chek status for a user.
        Returns a dict with direct_pay and card status information.
        """
        try:
            # Fetch user details to get latest direct pay and card info
            user_details = self.get_user(chek_user_id)

            current_app.logger.debug(f"Fetched provider details for Chek user {chek_user_id}: {user_details}")

            status = {
                "direct_pay_id": None,
                "direct_pay_status": None,
                "card_id": None,
                "card_status": None,
                "timestamp": datetime.now(timezone.utc),
                "wallet_balance": user_details.balance,
            }

            # Extract direct pay status
            if user_details.directpay:
                status["direct_pay_id"] = str(user_details.directpay.id)
                status["direct_pay_status"] = user_details.directpay.status

            # Extract card status (assuming first card is primary)
            if user_details.cards:
                first_card = user_details.cards[0]
                status["card_id"] = str(first_card.id)
                status["card_status"] = first_card.status

            return status

        except Exception as e:
            current_app.logger.error(f"Failed to fetch Chek status for provider user {chek_user_id}: {e}")
            sentry_sdk.capture_exception(e)
            raise

    def get_family_chek_status(self, chek_user_id: int) -> dict:
        """
        Fetches the current Chek status for a family.
        Returns a dict with direct_pay and card status information.
        """
        try:
            # Fetch family details to get latest direct pay and card info
            family_details = self.get_user(chek_user_id)

            current_app.logger.debug(f"Fetched family details for Chek user {chek_user_id}: {family_details}")

            status = {
                "timestamp": datetime.now(timezone.utc),
                "wallet_balance": family_details.balance,
            }
            return status

        except Exception as e:
            current_app.logger.error(f"Failed to fetch Chek status for family user {chek_user_id}: {e}")
            sentry_sdk.capture_exception(e)
            raise
