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

    def _sanitize_request_data(self, data):
        """
        Sanitize request data by masking sensitive fields for logging/debugging.
        Returns a copy with sensitive data masked.
        """
        if isinstance(data, list):
            return [self._sanitize_request_data(item) for item in data]

        if not isinstance(data, dict):
            return data

        # Fields to mask for security
        sensitive_fields = {
            "api_key",
            "api-key",
            "write-key",
            "write_key",
            "password",
            "token",
            "secret",
            "ssn",
            "social_security_number",
            "account_number",
            "routing_number",
            "card_number",
            "cvv",
            "pin",
            "bank_account",
            "tax_id",
        }

        sanitized = {}
        for key, value in data.items():
            key_lower = key.lower()

            # Check if key contains sensitive terms
            is_sensitive = any(sensitive_term in key_lower for sensitive_term in sensitive_fields)

            if is_sensitive:
                if isinstance(value, str) and len(value) > 4:
                    # Show first 2 and last 2 characters
                    sanitized[key] = f"{value[:2]}***{value[-2:]}"
                else:
                    sanitized[key] = "***"
            elif isinstance(value, dict):
                # Recursively sanitize nested dictionaries
                sanitized[key] = self._sanitize_request_data(value)
            else:
                sanitized[key] = value

        return sanitized

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
            log_message += f"  Headers: {self._sanitize_request_data(headers)}\n"
            if "json" in kwargs:
                log_message += f"  Body (JSON): {self._sanitize_request_data(kwargs['json'])}\n"
            elif "data" in kwargs:
                log_message += f"  Body (Form Data): {self._sanitize_request_data(kwargs['data'])}\n"

            logger.info(log_message)

            response = requests.request(method, url, headers=headers, **kwargs)
            logger.info(f"Full request URL (from requests object): {response.request.url}")
            response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)
            return response.json()
        except requests.exceptions.HTTPError as e:  # Catch HTTPError specifically
            # Build comprehensive error context for debugging
            error_context = {
                "method": method,
                "url": url,
                "status_code": e.response.status_code,
                "response_headers": self._sanitize_request_data(dict(e.response.headers)),
                "response_body": e.response.text,
                "request_headers": self._sanitize_request_data(dict(e.response.request.headers)),
            }

            # Add request body if present (but sanitize sensitive data)
            if "json" in kwargs:
                sanitized_body = self._sanitize_request_data(kwargs["json"])
                error_context["request_body"] = sanitized_body
            elif "data" in kwargs:
                sanitized_body = self._sanitize_request_data(kwargs["data"])
                error_context["request_body"] = sanitized_body

            # Log detailed error with context
            current_app.logger.error(
                f"Chek API HTTP Error: {e.response.status_code} - {e.response.text}\n"
                f"Request Context: {error_context}"
            )

            # Add context to Sentry
            with sentry_sdk.push_scope() as scope:
                scope.set_context("chek_api_error", error_context)
                scope.set_tag("chek_api_endpoint", endpoint)
                scope.set_tag("chek_api_method", method)
                scope.set_tag("chek_api_status", e.response.status_code)
                sentry_sdk.capture_exception(e)

            raise  # Re-raise the original exception

        except requests.exceptions.RequestException as e:  # Catch other request errors
            # Build error context for non-HTTP errors (connection, timeout, etc.)
            error_context = {
                "method": method,
                "url": url,
                "error_type": type(e).__name__,
            }

            # Add request body if present (but sanitize sensitive data)
            if "json" in kwargs:
                sanitized_body = self._sanitize_request_data(kwargs["json"])
                error_context["request_body"] = sanitized_body
            elif "data" in kwargs:
                sanitized_body = self._sanitize_request_data(kwargs["data"])
                error_context["request_body"] = sanitized_body

            current_app.logger.error(f"Chek API request failed: {e}\n" f"Request Context: {error_context}")

            # Add context to Sentry
            with sentry_sdk.push_scope() as scope:
                scope.set_context("chek_api_error", error_context)
                scope.set_tag("chek_api_endpoint", endpoint)
                scope.set_tag("chek_api_method", method)
                scope.set_tag("chek_error_type", type(e).__name__)
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

    def create_card(self, user_id, card_data):
        """
        Creates a new card for a user using the new endpoint.
        """
        endpoint = f"users/{user_id}/create_card/"
        return self._request("POST", endpoint, json=card_data)

    def list_programs(self):
        """
        Lists all programs for the account.
        """
        endpoint = f"programs/"
        return self._request("GET", endpoint)

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
        Transfers funds between wallets or program to wallet.
        """
        return self._request("POST", f"users/{user_id}/transfer_balance/", json=transfer_data)

    def send_ach_payment(self, user_id, payment_data):
        """
        Initiates a Same-Day ACH transfer to a recipient's linked bank account.
        """
        return self._request("POST", f"directpay_accounts/{user_id}/send_payment/", json=payment_data)

    def transfer_funds_to_card(self, card_id, transfer_data):
        """
        Transfers funds to or from a virtual card.
        """
        return self._request("POST", f"cards/{card_id}/transfer_balance/", json=transfer_data)
