import requests
import sentry_sdk
from flask import current_app


class ChekClient:
    """A client for interacting with the Chek API."""

    def __init__(self, config):
        self.base_url = config["CHEK_BASE_URL"]
        self.account_id = config["CHEK_ACCOUNT_ID"]
        self.api_key = config["CHEK_API_KEY"]
        self.write_key = config["CHEK_WRITE_KEY"]

    def _get_headers(self, is_write_operation=False):
        """Constructs the necessary headers for an API request."""
        headers = {"API-Key": self.api_key, "Content-Type": "application/json"}
        if is_write_operation:
            if not self.write_key:
                raise ValueError("CHEK_WRITE_KEY is not configured. It is required for write operations.")
            headers["Write-Key"] = self.write_key
        return headers

    def _request(self, method, endpoint, **kwargs):
        """
        Makes a request to the Chek API and handles the response.

        Args:
            method (str): The HTTP method (e.g., 'GET', 'POST').
            endpoint (str): The API endpoint to call.
            **kwargs: Additional keyword arguments to pass to the requests method.

        Returns:
            dict: The JSON response from the API.

        Raises:
            Exception: If the request fails.
        """
        url = f"{self.base_url}/api/v1/account/{self.account_id}/{endpoint}"
        is_write = method.upper() in ["POST", "PATCH"]
        headers = self._get_headers(is_write_operation=is_write)

        try:
            logger = current_app.logger

            # Prepare detailed log message
            log_message = f"Chek API Request Details:\n"
            log_message += f"  Method: {method}\n"
            log_message += f"  URL: {url}\n"
            log_message += f"  Headers: {headers}\n"
            if "json" in kwargs:
                log_message += f"  Body (JSON): {kwargs['json']}\n"
            elif "data" in kwargs:
                log_message += f"  Body (Form Data): {kwargs['data']}\n"

            logger.info(log_message)

            response = requests.request(method, url, headers=headers, **kwargs)
            logger.info(f"Full request URL (from requests object): {response.request.url}")
            response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)
            return response.json()
        except requests.exceptions.HTTPError as e:  # Catch HTTPError specifically
            current_app.logger.error(
                f"Chek API HTTP Error: {e.response.status_code} - {e.response.text}"
            )  # Log response body
            sentry_sdk.capture_exception(e)
            raise  # Re-raise the original exception
        except requests.exceptions.RequestException as e:  # Catch other request errors
            current_app.logger.error(f"Chek API request failed: {e}")
            sentry_sdk.capture_exception(e)
            raise

    def list_users(self, email=None):
        """
        Lists users, optionally filtering by email.
        """
        params = {}
        if email:
            params["email"] = email
        return self._request("GET", "users/", params=params)

    def create_user(self, user_data):
        """
        Creates a new user.
        """
        return self._request("POST", "users/", json=user_data)

    def get_user(self, user_id):
        """
        Retrieves a specific user by their ID.
        """
        return self._request("GET", f"users/{user_id}/")

    def create_card(self, card_data):
        """
        Creates a new card for a user.
        """
        return self._request("POST", "cards/", json=card_data)

    def get_card(self, card_id):
        """
        Retrieves a specific card by its ID.
        """
        return self._request("GET", f"cards/{card_id}/")

    def create_direct_pay_account_invite(self, user_id):
        """
        Invites a user to create a direct pay account.
        """
        return self._request("POST", "directpay_accounts/invite/", json={"user_id": user_id})

    def get_direct_pay_account(self, account_id):
        """
        Retrieves a specific direct pay account by its ID.
        """
        return self._request("GET", f"directpay_accounts/{account_id}/")

    def transfer_balance(self, user_id, transfer_data):
        """
        Transfers balance between users or accounts.
        """
        return self._request(
            "POST", f"public_admin/accounts/{self.account_id}/users/{user_id}/transfer_balance", json=transfer_data
        )
