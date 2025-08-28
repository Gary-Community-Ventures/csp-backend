import re
from datetime import datetime, timezone
from typing import Optional, Union

import sentry_sdk
from flask import current_app

from app.config import CARE_DAYS_SAMPLE_SIZE, MAX_PAYMENT_AMOUNT_CENTS
from app.enums.payment_method import PaymentMethod
from app.exceptions import (
    AllocationExceededException,
    DataNotFoundException,
    InvalidPaymentStateException,
    PaymentLimitExceededException,
    PaymentMethodNotConfiguredException,
    ProviderNotFoundException,
    ProviderNotPayableException,
)
from app.extensions import db
from app.integrations.chek.schemas import (
    ACHFundingSource,
    ACHPaymentRequest,
    ACHPaymentType,
)
from app.integrations.chek.service import (
    ChekService as ChekIntegrationService,  # Avoid name collision
)
from app.models import (
    AllocatedCareDay,
    AllocatedLumpSum,
    MonthAllocation,
    Payment,
    PaymentAttempt,
    ProviderPaymentSettings,
)
from app.services.payment_result import PaymentResult


def format_phone_to_e164(phone: Optional[str], default_country: str = "US") -> Optional[str]:
    """
    Format a phone number to E.164 format for Chek API.

    Args:
        phone: Phone number string in various formats
        default_country: Default country code if not provided (US = +1)

    Returns:
        Phone number in E.164 format (e.g., +13035551234) or None if invalid
    """
    if not phone:
        return None

    # Remove all non-digit characters
    digits = re.sub(r"\D", "", phone)

    # If empty after cleaning, return None
    if not digits:
        return None

    # Handle US numbers (default)
    if default_country == "US":
        # If it starts with 1 and is 11 digits, it's already formatted
        if len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"
        # If it's 10 digits, add US country code
        elif len(digits) == 10:
            return f"+1{digits}"
        # If it's less than 10 digits, it's invalid
        else:
            return None

    # For other countries, you'd add their logic here
    # For now, just prepend + if not present
    return f"+{digits}" if not digits.startswith("+") else digits


class PaymentService:
    """
    Service for orchestrating payment processing, including Chek integration,
    database updates, and retry logic.
    """

    def __init__(self, app):
        self.chek_service = ChekIntegrationService(app)
        self.app = app

    def _create_payment_intent(
        self,
        provider_payment_settings: ProviderPaymentSettings,
        amount_cents: int,
        month_allocation: MonthAllocation,
        external_provider_id: str,
        external_child_id: str,
        allocated_care_days: Optional[list[AllocatedCareDay]] = None,
        allocated_lump_sums: Optional[list[AllocatedLumpSum]] = None,
    ) -> "PaymentIntent":
        """
        Creates a PaymentIntent capturing what we're trying to pay for.
        """
        from app.models.payment_intent import PaymentIntent

        # Extract IDs for storage
        care_day_ids = [day.id for day in (allocated_care_days or [])]
        lump_sum_ids = [lump.id for lump in (allocated_lump_sums or [])]

        # Build description
        payment_type = "care_days" if allocated_care_days else "lump_sum" if allocated_lump_sums else "other"
        description = f"Payment to provider {external_provider_id} for {payment_type}"

        intent = PaymentIntent(
            provider_external_id=external_provider_id,
            child_external_id=external_child_id,
            month_allocation_id=month_allocation.id,
            amount_cents=amount_cents,
            care_day_ids=care_day_ids,
            lump_sum_ids=lump_sum_ids,
            provider_payment_settings_id=provider_payment_settings.id,
            description=description,
        )
        db.session.add(intent)
        db.session.flush()
        return intent

    def _create_payment_attempt(
        self,
        intent: "PaymentIntent",
        payment_method: PaymentMethod,
        attempt_number: int = None,
    ) -> PaymentAttempt:
        """
        Creates a new PaymentAttempt for a PaymentIntent.
        """
        if attempt_number is None:
            attempt_number = len(intent.attempts) + 1

        attempt = PaymentAttempt(
            payment_intent_id=intent.id,
            attempt_number=attempt_number,
            payment_method=payment_method,
        )
        db.session.add(attempt)
        db.session.flush()
        return attempt

    def _create_payment_on_success(
        self,
        intent: "PaymentIntent",
        attempt: PaymentAttempt,
    ) -> Payment:
        """
        Creates a Payment record ONLY when payment succeeds.
        Links to the intent and successful attempt, marks items as paid.
        """
        provider_payment_settings = intent.provider_payment_settings

        payment = Payment(
            payment_intent_id=intent.id,
            successful_attempt_id=attempt.id,
            provider_payment_settings_id=provider_payment_settings.id,
            chek_user_id=provider_payment_settings.chek_user_id,
            chek_direct_pay_id=provider_payment_settings.chek_direct_pay_id,
            chek_card_id=provider_payment_settings.chek_card_id,
            amount_cents=intent.amount_cents,
            payment_method=attempt.payment_method,
            month_allocation_id=intent.month_allocation_id,
            external_provider_id=intent.provider_external_id,
            external_child_id=intent.child_external_id,
            chek_transfer_id=attempt.wallet_transfer_id,  # Store the successful transfer ID
        )
        db.session.add(payment)
        db.session.flush()

        # Link the successful attempt to the payment
        attempt.payment = payment

        # Get and mark care days/lump sums as paid
        allocated_care_days = intent.get_care_days()
        allocated_lump_sums = intent.get_lump_sums()

        if allocated_care_days:
            for day in allocated_care_days:
                day.payment = payment
                day.last_submitted_at = datetime.now(timezone.utc)
                day.payment_distribution_requested = True

        if allocated_lump_sums:
            for lump_sum in allocated_lump_sums:
                lump_sum.payment = payment
                lump_sum.submitted_at = datetime.now(timezone.utc)
                lump_sum.paid_at = datetime.now(timezone.utc)

        return payment

    def _execute_payment_flow(
        self,
        attempt: PaymentAttempt,
        intent: "PaymentIntent",
        provider_payment_settings: "ProviderPaymentSettings",
    ) -> bool:
        """
        Execute the payment flow: Program->Wallet transfer, then optionally ACH.
        Returns True if successful (including partial success for ACH with wallet funded).
        """
        from app.integrations.chek.schemas import (
            ACHFundingSource,
            ACHPaymentRequest,
            ACHPaymentType,
            FlowDirection,
            TransferBalanceRequest,
        )

        # Get care days and lump sums for metadata
        allocated_care_days = intent.get_care_days()
        allocated_lump_sums = intent.get_lump_sums()

        # Build description and metadata for tracking
        payment_type = "care_days" if allocated_care_days else "lump_sum" if allocated_lump_sums else "other"
        description = f"Payment to provider {intent.provider_external_id} for {payment_type}"

        metadata = {
            "provider_id": intent.provider_external_id,
            "child_id": intent.child_external_id,
            "payment_type": payment_type,
            "intent_id": str(intent.id),
        }

        # Add month/date info based on payment type
        if allocated_care_days:
            dates = [day.date.isoformat() for day in allocated_care_days[:5]]  # First 5 dates as sample
            metadata["care_dates_sample"] = dates
            metadata["care_days_count"] = len(allocated_care_days)
        if intent.month_allocation:
            metadata["allocation_month"] = intent.month_allocation.date.strftime("%Y-%m")

        # 1. Initiate Chek transfer (Program to Wallet)
        transfer_request = TransferBalanceRequest(
            flow_direction=FlowDirection.PROGRAM_TO_WALLET.value,
            program_id=self.chek_service.program_id,
            counterparty_id=self.chek_service.program_id,
            amount=intent.amount_cents,
            description=description,
            metadata=metadata,
        )
        transfer_response = self.chek_service.transfer_balance(
            user_id=int(provider_payment_settings.chek_user_id), request=transfer_request
        )

        # Record successful wallet funding
        self._update_payment_attempt_facts(attempt, wallet_transfer_id=str(transfer_response.transfer.id))

        # 2. If ACH, initiate ACH payment from wallet to bank account
        if provider_payment_settings.payment_method == PaymentMethod.ACH:
            if not provider_payment_settings.chek_direct_pay_id:
                raise PaymentMethodNotConfiguredException("Provider has no direct pay account ID for ACH payment")

            ach_request = ACHPaymentRequest(
                amount=intent.amount_cents,
                type=ACHPaymentType.SAME_DAY_ACH,
                funding_source=ACHFundingSource.WALLET_BALANCE,
            )

            ach_response = self.chek_service.send_ach_payment(
                direct_pay_account_id=provider_payment_settings.chek_direct_pay_id, request=ach_request
            )

            # Record successful ACH payment
            self._update_payment_attempt_facts(
                attempt, ach_payment_id=str(ach_response.id) if hasattr(ach_response, "id") else "ach_completed"
            )

            current_app.logger.info(
                f"ACH payment initiated for provider {provider_payment_settings.id}. DirectPayAccount status: {ach_response.status}"
            )

        # 3. Create Payment record ONLY if attempt is successful
        if attempt.is_successful:
            # NOW create the Payment record since payment succeeded
            payment = self._create_payment_on_success(
                intent=intent,
                attempt=attempt,
            )

            db.session.commit()
            current_app.logger.info(f"Payment {payment.id} processed successfully for Intent {intent.id}.")
            return True
        else:
            # For ACH payments that only completed wallet transfer (partial success)
            # NO Payment record created yet - will be created when ACH completes via retry
            db.session.commit()
            current_app.logger.info(f"Payment Intent {intent.id} partially completed - wallet funded, ACH pending.")
            return True  # Still considered success since wallet is funded

    def _update_payment_attempt_facts(
        self,
        attempt: PaymentAttempt,
        wallet_transfer_id: Optional[str] = None,
        ach_payment_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ):
        """
        Updates the facts of what happened in a PaymentAttempt.
        """
        if wallet_transfer_id:
            attempt.wallet_transfer_id = wallet_transfer_id
            attempt.wallet_transfer_at = datetime.now(timezone.utc)
        if ach_payment_id:
            attempt.ach_payment_id = ach_payment_id
            attempt.ach_payment_at = datetime.now(timezone.utc)
        if error_message:
            attempt.error_message = error_message
        db.session.add(attempt)

    def process_payment(
        self,
        external_provider_id: str,
        external_child_id: str,
        month_allocation: MonthAllocation,
        allocated_care_days: Optional[list[AllocatedCareDay]] = None,
        allocated_lump_sums: Optional[list[AllocatedLumpSum]] = None,
    ) -> Union[bool, PaymentResult]:
        """
        Orchestrates the payment process for a provider.
        Calculates the amount from the allocations and uses the provider's configured payment method.

        Returns:
            bool: True if payment succeeded, False otherwise (for backward compatibility)
            In future versions, will return PaymentResult for more details
        """
        try:
            # 1. Look up provider payment settings
            provider_payment_settings = ProviderPaymentSettings.query.filter_by(
                provider_external_id=external_provider_id
            ).first()
            if not provider_payment_settings:
                error_msg = f"Provider with external ID {external_provider_id} not found in database"
                current_app.logger.error(f"Payment failed: {error_msg}")
                raise ProviderNotFoundException(error_msg)

            # 2. Calculate amount from allocations
            amount_cents = 0
            if allocated_care_days:
                amount_cents += sum(day.amount_cents for day in allocated_care_days)
            if allocated_lump_sums:
                amount_cents += sum(lump.amount_cents for lump in allocated_lump_sums)
            if amount_cents <= 0:
                raise InvalidPaymentStateException("No allocations provided for payment")

            # 3. Validate all allocated items are submitted
            if allocated_care_days:
                unsubmitted_days = [day for day in allocated_care_days if day.last_submitted_at is None]
                if unsubmitted_days:
                    error_msg = f"Cannot process payment: {len(unsubmitted_days)} care days are not submitted"
                    current_app.logger.error(f"Payment failed for Provider {provider_payment_settings.id}: {error_msg}")
                    raise InvalidPaymentStateException(error_msg)

            if allocated_lump_sums:
                unsubmitted_lumps = [lump for lump in allocated_lump_sums if lump.submitted_at is None]
                if unsubmitted_lumps:
                    error_msg = f"Cannot process payment: {len(unsubmitted_lumps)} lump sums are not submitted"
                    current_app.logger.error(f"Payment failed for Provider {provider_payment_settings.id}: {error_msg}")
                    raise InvalidPaymentStateException(error_msg)

            # 4. Validate payment doesn't exceed $1400 limit
            if amount_cents > MAX_PAYMENT_AMOUNT_CENTS:
                error_msg = (
                    f"Payment amount ${amount_cents / 100:.2f} exceeds maximum allowed payment "
                    f"of ${MAX_PAYMENT_AMOUNT_CENTS / 100:.2f}"
                )
                current_app.logger.error(f"Payment failed for Provider {provider_payment_settings.id}: {error_msg}")
                raise PaymentLimitExceededException(error_msg)

            # 5. Validate payment doesn't exceed remaining allocation
            if amount_cents > month_allocation.remaining_to_pay_cents:
                error_msg = (
                    f"Payment amount {amount_cents} cents exceeds remaining allocation "
                    f"{month_allocation.remaining_to_pay_cents} cents for month {month_allocation.date.strftime('%Y-%m')}"
                )
                current_app.logger.error(f"Payment failed for Provider {provider_payment_settings.id}: {error_msg}")
                raise AllocationExceededException(error_msg)

            # 6. Ensure provider has a payment method configured
            if not provider_payment_settings.payment_method:
                error_msg = f"Provider {external_provider_id} has no payment method configured"
                current_app.logger.error(f"Payment failed for Provider {provider_payment_settings.id}: {error_msg}")
                raise PaymentMethodNotConfiguredException(error_msg)

            # 7. Refresh provider Chek status to ensure freshness
            self.refresh_provider_settings(provider_payment_settings)
            db.session.flush()  # Ensure provider object is updated in session

            # 8. Create PaymentIntent to capture what we're trying to pay for
            intent = self._create_payment_intent(
                provider_payment_settings=provider_payment_settings,
                amount_cents=amount_cents,
                month_allocation=month_allocation,
                external_provider_id=external_provider_id,
                external_child_id=external_child_id,
                allocated_care_days=allocated_care_days,
                allocated_lump_sums=allocated_lump_sums,
            )

            # 9. Validate payment method status with detailed error messages
            is_valid, validation_error = provider_payment_settings.validate_payment_method_status()
            if not is_valid:
                current_app.logger.warning(
                    f"Payment skipped for Provider {provider_payment_settings.id}: {validation_error}"
                )
                # Create a failed attempt for the intent
                attempt = self._create_payment_attempt(
                    intent=intent,
                    payment_method=provider_payment_settings.payment_method,
                )
                self._update_payment_attempt_facts(attempt, error_message=validation_error)
                db.session.commit()
                return False

            # 10. Create PaymentAttempt for this intent
            attempt = self._create_payment_attempt(
                intent=intent,
                payment_method=provider_payment_settings.payment_method,
            )

            try:
                # Execute payment flow
                success = self._execute_payment_flow(
                    attempt=attempt,
                    intent=intent,
                    provider_payment_settings=provider_payment_settings,
                )

                if success:
                    return True
                else:
                    return False

            except Exception as payment_execution_error:
                # Record the error in the attempt
                self._update_payment_attempt_facts(attempt, error_message=str(payment_execution_error))
                db.session.commit()  # Always save the attempt record
                current_app.logger.error(
                    f"Payment execution failed for Provider {provider_payment_settings.id}: {payment_execution_error}"
                )
                sentry_sdk.capture_exception(payment_execution_error)
                return False

        except (
            ProviderNotFoundException,
            InvalidPaymentStateException,
            PaymentLimitExceededException,
            AllocationExceededException,
            PaymentMethodNotConfiguredException,
            ProviderNotPayableException,
        ) as e:
            # Business logic exceptions - still send to Sentry for monitoring during early rollout
            db.session.rollback()
            current_app.logger.error(f"Payment validation failed for {external_provider_id}: {type(e).__name__}: {e}")
            sentry_sdk.capture_exception(e)
            return False
        except Exception as e:
            # Unexpected errors
            db.session.rollback()
            current_app.logger.error(f"Unexpected error processing payment for {external_provider_id}: {e}")
            sentry_sdk.capture_exception(e)
            return False

    def retry_payment_intent(self, intent_id: str) -> bool:
        """
        Retry a payment for a PaymentIntent.
        Handles both full retries and ACH-only retries (where wallet is already funded).
        """
        from app.models.payment_intent import PaymentIntent

        try:
            # Get the intent
            intent = PaymentIntent.query.get(intent_id)
            if not intent:
                current_app.logger.error(f"PaymentIntent {intent_id} not found")
                return False

            # Check if already paid
            if intent.is_paid:
                current_app.logger.info(f"PaymentIntent {intent_id} is already paid")
                return True

            # Check if we can retry
            if not intent.can_retry:
                current_app.logger.error(f"PaymentIntent {intent_id} cannot be retried")
                return False

            provider_payment_settings = intent.provider_payment_settings

            # Find the latest attempt to determine retry strategy
            last_attempt = intent.latest_attempt

            # Determine if we need full payment or just ACH completion
            if (
                last_attempt
                and last_attempt.payment_method == PaymentMethod.ACH
                and last_attempt.wallet_transfer_id
                and not last_attempt.ach_payment_id
            ):
                # Wallet funded but ACH incomplete - just retry ACH
                current_app.logger.info(f"Retrying ACH completion for Intent {intent_id} (wallet already funded)")

                # Create new attempt that continues from the wallet-funded state
                new_attempt = self._create_payment_attempt(
                    intent=intent,
                    payment_method=PaymentMethod.ACH,
                )

                # Copy wallet funding info from previous attempt
                new_attempt.wallet_transfer_id = last_attempt.wallet_transfer_id
                new_attempt.wallet_transfer_at = last_attempt.wallet_transfer_at

                try:
                    # Just do the ACH part
                    ach_request = ACHPaymentRequest(
                        amount=intent.amount_cents,
                        type=ACHPaymentType.SAME_DAY_ACH,
                        funding_source=ACHFundingSource.WALLET_BALANCE,
                    )

                    if not provider_payment_settings.chek_direct_pay_id:
                        raise PaymentMethodNotConfiguredException(
                            "Provider has no direct pay account ID for ACH payment"
                        )

                    ach_response = self.chek_service.send_ach_payment(
                        direct_pay_account_id=provider_payment_settings.chek_direct_pay_id, request=ach_request
                    )

                    # Record successful ACH
                    self._update_payment_attempt_facts(
                        new_attempt,
                        ach_payment_id=str(ach_response.id) if hasattr(ach_response, "id") else "ach_completed",
                    )

                    # Create Payment record since now it's complete
                    payment = self._create_payment_on_success(
                        intent=intent,
                        attempt=new_attempt,
                    )

                    db.session.commit()
                    current_app.logger.info(
                        f"ACH retry successful for Intent {intent_id}, Payment {payment.id} created"
                    )
                    return True

                except Exception as e:
                    self._update_payment_attempt_facts(new_attempt, error_message=str(e))
                    db.session.commit()
                    current_app.logger.error(f"ACH retry failed for Intent {intent_id}: {e}")
                    sentry_sdk.capture_exception(e)
                    return False

            else:
                # Need full payment retry (start from scratch)
                current_app.logger.info(f"Retrying full payment for Intent {intent_id}")

                # Create new attempt
                new_attempt = self._create_payment_attempt(
                    intent=intent,
                    payment_method=provider_payment_settings.payment_method,
                )

                # Refresh provider status
                try:
                    self.refresh_provider_settings(provider_payment_settings)
                except Exception as e:
                    current_app.logger.warning(f"Failed to refresh provider status during retry: {e}")
                    # Continue with retry anyway

                # Validate payment method status
                is_valid, validation_error = provider_payment_settings.validate_payment_method_status()
                if not is_valid:
                    self._update_payment_attempt_facts(
                        new_attempt,
                        error_message=validation_error,
                    )
                    db.session.commit()
                    return False

                # Execute full payment flow
                try:
                    success = self._execute_payment_flow(
                        attempt=new_attempt,
                        intent=intent,
                        provider_payment_settings=provider_payment_settings,
                    )

                    if success:
                        current_app.logger.info(f"Full payment retry successful for Intent {intent_id}")
                        return True
                    else:
                        current_app.logger.warning(f"Full payment retry failed for Intent {intent_id}")
                        return False

                except Exception as payment_error:
                    self._update_payment_attempt_facts(new_attempt, error_message=str(payment_error))
                    db.session.commit()
                    current_app.logger.error(f"Full payment retry failed for Intent {intent_id}: {payment_error}")
                    sentry_sdk.capture_exception(payment_error)
                    return False

            # Handle ACH-only retry (wallet already funded)
            try:
                ach_request = ACHPaymentRequest(
                    amount=intent.amount_cents,
                    type=ACHPaymentType.SAME_DAY_ACH,
                    funding_source=ACHFundingSource.WALLET_BALANCE,
                )

                if not provider_payment_settings.chek_direct_pay_id:
                    raise PaymentMethodNotConfiguredException("Provider has no direct pay account ID for ACH payment")

                ach_response = self.chek_service.send_ach_payment(
                    direct_pay_account_id=provider_payment_settings.chek_direct_pay_id, request=ach_request
                )

                # Record successful ACH payment
                self._update_payment_attempt_facts(
                    ach_retry_attempt,
                    ach_payment_id=str(ach_response.id) if hasattr(ach_response, "id") else "ach_completed",
                )

                # Create Payment record on success
                self._create_payment_on_success(intent, ach_retry_attempt)

                db.session.commit()
                current_app.logger.info(f"ACH payment retry successful for Intent {intent_id}")
                return True

            except Exception as ach_error:
                # Record the ACH failure
                self._update_payment_attempt_facts(ach_retry_attempt, error_message=str(ach_error))
                db.session.commit()
                current_app.logger.error(f"ACH retry failed for Intent {intent_id}: {ach_error}")
                sentry_sdk.capture_exception(ach_error)
                return False

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error retrying payment for Intent {intent_id}: {e}")
            sentry_sdk.capture_exception(e)
            return False

    def initialize_provider_payment(self, provider_external_id: str, payment_method: str) -> dict:
        """
        Initialize a provider's payment method (card or ACH).

        Args:
            provider_external_id: Provider ID from Google Sheets
            payment_method: Either "card" or "ach"

        Returns:
            dict with status and details of the initialization
        """
        from app.integrations.chek.schemas import (
            CardCreateRequest,
            DirectPayAccountInviteRequest,
        )
        from app.sheets.mappings import ProviderColumnNames, get_provider, get_providers

        try:
            # Ensure provider is onboarded to Chek
            provider_settings = ProviderPaymentSettings.query.filter_by(
                provider_external_id=provider_external_id
            ).first()

            if not provider_settings:
                # Onboard the provider to Chek
                provider_settings = self.onboard_provider(provider_external_id=provider_external_id)
                current_app.logger.info(f"Onboarded provider {provider_external_id} to Chek")

            if not provider_settings.chek_user_id:
                raise PaymentMethodNotConfiguredException("Provider has no Chek user ID")

            result = {
                "provider_id": provider_external_id,
                "chek_user_id": provider_settings.chek_user_id,
                "payment_method": payment_method,
            }

            if payment_method == "card":
                # Check if card already exists
                if provider_settings.chek_card_id:
                    result["message"] = "Provider already has a virtual card"
                    result["card_id"] = provider_settings.chek_card_id
                    result["already_exists"] = True
                    return result

                # Get program ID from config
                chek_program_id = current_app.config.get("CHEK_PROGRAM_ID")

                if not chek_program_id:
                    raise PaymentMethodNotConfiguredException("CHEK_PROGRAM_ID not configured")

                # Create virtual card with wallet balance funding
                card_request = CardCreateRequest(
                    program_id=int(chek_program_id),
                    funding_method="program_balance",
                    amount=1000,  # Initial amount in cents
                )

                card_response = self.chek_service.create_card(int(provider_settings.chek_user_id), card_request)

                # Extract card ID from the response
                card_id = card_response.card.get("id")
                card_status = card_response.card.get("status", "Active")
                # Update provider settings with card info
                provider_settings.chek_card_id = str(card_id)
                provider_settings.chek_card_status = card_status
                provider_settings.payment_method = PaymentMethod.CARD
                provider_settings.payment_method_updated_at = datetime.now(timezone.utc)
                provider_settings.last_chek_sync_at = datetime.now(timezone.utc)
                db.session.commit()

                result["message"] = "Virtual card created successfully"
                result["card_id"] = card_id

            else:  # ACH
                # Check if ACH already exists
                if provider_settings.chek_direct_pay_id:
                    result["message"] = "Provider already has ACH set up"
                    result["direct_pay_id"] = provider_settings.chek_direct_pay_id
                    result["already_exists"] = True
                    return result

                # Get provider email from Google Sheets
                provider_rows = get_providers()
                provider_data = get_provider(provider_external_id, provider_rows)

                if not provider_data:
                    raise ProviderNotFoundException(f"Provider {provider_external_id} not found in Google Sheets")

                provider_email = provider_data.get(ProviderColumnNames.EMAIL)
                if not provider_email:
                    raise DataNotFoundException(f"Provider {provider_external_id} has no email address")

                # Send ACH invite
                invite_request = DirectPayAccountInviteRequest(user_id=int(provider_settings.chek_user_id))

                invite_response = self.chek_service.invite_direct_pay_account(invite_request)

                # The API returns a string message, not an object
                # Update provider settings with pending ACH info
                provider_settings.chek_direct_pay_id = None  # Will be set when user completes setup
                provider_settings.chek_direct_pay_status = "Pending"  # Invite sent but not completed
                provider_settings.payment_method = PaymentMethod.ACH
                provider_settings.payment_method_updated_at = datetime.now(timezone.utc)
                provider_settings.last_chek_sync_at = datetime.now(timezone.utc)
                db.session.commit()

                result["message"] = "ACH invite sent successfully"
                result["invite_response"] = invite_response
                result["invite_sent_to"] = provider_email

            return result

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Failed to initialize payment for provider {provider_external_id}: {e}")
            raise

    def refresh_provider_settings(self, provider_payment_settings: ProviderPaymentSettings):
        """
        Refreshes the Chek status of a provider and updates the database.
        """
        if not provider_payment_settings.chek_user_id:
            current_app.logger.warning(
                f"Provider {provider_payment_settings.id} has no chek_user_id. Cannot refresh status."
            )
            return

        try:
            # Get status from Chek API
            status = self.chek_service.get_provider_chek_status(int(provider_payment_settings.chek_user_id))

            # Update provider with new status
            provider_payment_settings.chek_direct_pay_id = status["direct_pay_id"]
            provider_payment_settings.chek_direct_pay_status = status["direct_pay_status"]
            provider_payment_settings.chek_card_id = status["card_id"]
            provider_payment_settings.chek_card_status = status["card_status"]
            provider_payment_settings.chek_wallet_balance = status.get(
                "wallet_balance", provider_payment_settings.chek_wallet_balance
            )
            provider_payment_settings.last_chek_sync_at = status["timestamp"]

            db.session.add(provider_payment_settings)
            db.session.commit()
            current_app.logger.info(f"Provider {provider_payment_settings.id} Chek status refreshed successfully.")

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Failed to refresh Chek status for provider {provider_payment_settings.id}: {e}")
            sentry_sdk.capture_exception(e)

    def onboard_provider(self, provider_external_id: str) -> ProviderPaymentSettings:
        """
        Onboards a new provider by creating a Chek user and ProviderPaymentSettings record.
        """
        import uuid

        from app.integrations.chek.schemas import Address, UserCreateRequest
        from app.sheets.mappings import ProviderColumnNames, get_provider, get_providers

        try:
            # Check if provider already exists
            existing_provider_payment_settings = ProviderPaymentSettings.query.filter_by(
                provider_external_id=provider_external_id
            ).first()

            if existing_provider_payment_settings:
                current_app.logger.info(
                    f"Provider {provider_external_id} already exists with Chek user {existing_provider_payment_settings.chek_user_id}"
                )
                return existing_provider_payment_settings

            # Get provider data from Google Sheets
            provider_rows = get_providers()
            provider_data = get_provider(provider_external_id, provider_rows)

            if not provider_data:
                raise ProviderNotFoundException(f"Provider {provider_external_id} not found in Google Sheets")

            # Extract provider information
            provider_email = provider_data.get(ProviderColumnNames.EMAIL)
            provider_phone_raw = provider_data.get(ProviderColumnNames.PHONE_NUMBER)
            first_name = provider_data.get(ProviderColumnNames.FIRST_NAME)
            last_name = provider_data.get(ProviderColumnNames.LAST_NAME)
            address_line1 = provider_data.get(ProviderColumnNames.ADDRESS_LINE1)
            address_line2 = provider_data.get(ProviderColumnNames.ADDRESS_LINE2)
            city = provider_data.get(ProviderColumnNames.CITY)
            state = provider_data.get(ProviderColumnNames.STATE)
            zip_code = provider_data.get(ProviderColumnNames.ZIP_CODE)
            country_code = provider_data.get(ProviderColumnNames.COUNTRY_CODE)

            if not provider_email:
                raise DataNotFoundException(f"Provider {provider_external_id} has no email in Google Sheets")

            # Format phone number to E.164 format
            provider_phone = format_phone_to_e164(provider_phone_raw)
            if not provider_phone:
                raise DataNotFoundException(
                    f"Provider {provider_external_id} has invalid phone number: {provider_phone_raw}"
                )

            # Check if Chek user already exists with this email
            existing_chek_user = self.chek_service.get_user_by_email(provider_email)

            if existing_chek_user:
                # User already exists in Chek, just create the ProviderPaymentSettings
                current_app.logger.info(
                    f"Chek user already exists for email {provider_email}, linking to provider {provider_external_id}"
                )
                chek_user_id = str(existing_chek_user.id)
            else:
                # Create new Chek user
                user_request = UserCreateRequest(
                    email=provider_email,
                    phone=provider_phone,
                    first_name=first_name,
                    last_name=last_name,
                    address=Address(
                        line1=address_line1 or "",
                        line2=address_line2 or "",
                        city=city or "",
                        state=state or "",
                        postal_code=zip_code or "",
                        country_code=country_code or "US",
                    ),
                )

                chek_user_response = self.chek_service.create_user(user_request)
                current_app.logger.info(
                    f"Created Chek user {chek_user_response.id} for provider {provider_external_id}"
                )
                chek_user_id = str(chek_user_response.id)

            # Create ProviderPaymentSettings record
            provider_payment_settings = ProviderPaymentSettings(
                id=uuid.uuid4(),
                provider_external_id=provider_external_id,
                chek_user_id=chek_user_id,
                payment_method=None,  # Provider chooses this later
                chek_wallet_balance=chek_user_response.balance,
            )
            db.session.add(provider_payment_settings)
            db.session.commit()

            current_app.logger.info(
                f"Successfully onboarded provider {provider_external_id} with Chek user {chek_user_id}"
            )
            return provider_payment_settings

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Failed to onboard provider {provider_external_id}: {e}")
            sentry_sdk.capture_exception(e)
            raise
