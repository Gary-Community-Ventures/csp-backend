from datetime import date, datetime, timezone
from typing import Optional, Union

import sentry_sdk
from flask import current_app

from app.constants import MAX_PAYMENT_AMOUNT_CENTS
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
    TransferBalanceResponse,
)
from app.integrations.chek.service import (
    ChekService as ChekIntegrationService,  # Avoid name collision
)
from app.models import (
    AllocatedCareDay,
    AllocatedLumpSum,
    FamilyPaymentSettings,
    MonthAllocation,
    Payment,
    PaymentAttempt,
    ProviderPaymentSettings,
)
from app.services.payment.family_onboarding import FamilyOnboarding
from app.services.payment.provider_onboarding import ProviderOnboarding
from app.services.payment.schema import PaymentResult
from app.supabase.helpers import cols, format_name, unwrap_or_abort, unwrap_or_error
from app.supabase.tables import Child, Provider


class PaymentService:
    """
    Service for orchestrating payment processing
    """

    def __init__(self, app):
        self.chek_service = ChekIntegrationService(app)
        self.app = app
        self.provider_onboarding = ProviderOnboarding(self.chek_service)
        self.family_onboarding = FamilyOnboarding(self.chek_service)

    def _get_types(
        self,
        allocated_care_days: Optional[list[AllocatedCareDay]] = None,
        allocated_lump_sums: Optional[list[AllocatedLumpSum]] = None,
    ) -> list[str]:
        """Determine the types of allocations being paid for"""
        types = []
        if allocated_care_days:
            types.append("care_days")
        if allocated_lump_sums:
            types.append("lump_sum")
        return types

    def _generate_description(
        self,
        external_provider_id: str,
        allocated_care_days: Optional[list[AllocatedCareDay]] = None,
        allocated_lump_sums: Optional[list[AllocatedLumpSum]] = None,
    ) -> str:
        """
        Generate a description for the payment intent based on the allocated items.
        """
        payment_types = self._get_types(allocated_care_days, allocated_lump_sums)

        payment_type = " and ".join(payment_types) if payment_types else "other"
        return f"Payment to provider {external_provider_id} for {payment_type}"

    def _create_payment_intent(
        self,
        provider_payment_settings: ProviderPaymentSettings,
        family_payment_settings: FamilyPaymentSettings,
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
        description = self._generate_description(external_provider_id, allocated_care_days, allocated_lump_sums)

        intent = PaymentIntent(
            provider_external_id=external_provider_id,
            child_external_id=external_child_id,
            month_allocation_id=month_allocation.id,
            amount_cents=amount_cents,
            care_day_ids=care_day_ids,
            lump_sum_ids=lump_sum_ids,
            provider_payment_settings_id=provider_payment_settings.id,
            family_payment_settings_id=family_payment_settings.id,
            description=description,
        )
        db.session.add(intent)
        db.session.flush()
        return intent

    def _create_payment_attempt(
        self,
        intent: "PaymentIntent",
        payment_method: PaymentMethod,
        provider_payment_settings: "ProviderPaymentSettings",
        family_payment_settings: "FamilyPaymentSettings",
    ) -> PaymentAttempt:
        """
        Creates a new PaymentAttempt for a PaymentIntent.
        Captures payment instrument IDs from provider settings at time of attempt.
        """
        attempt_number = len(intent.attempts) + 1

        attempt = PaymentAttempt(
            payment_intent_id=intent.id,
            attempt_number=attempt_number,
            payment_method=payment_method,
        )

        # Capture payment instrument IDs at time of attempt
        attempt.provider_chek_user_id = provider_payment_settings.chek_user_id
        attempt.family_chek_user_id = family_payment_settings.chek_user_id
        if payment_method == PaymentMethod.CARD:
            attempt.provider_chek_card_id = provider_payment_settings.chek_card_id
        elif payment_method == PaymentMethod.ACH:
            attempt.provider_chek_direct_pay_id = provider_payment_settings.chek_direct_pay_id

        db.session.add(attempt)
        db.session.flush()
        return attempt

    def _create_payment_on_success(
        self,
        intent: "PaymentIntent",
        attempt: PaymentAttempt,
    ) -> Payment:
        """
        Creates a Payment record ONLY when payment attempt succeeds.
        Links to the intent and successful attempt, marks items as paid.
        """
        from app.utils.email_service import send_payment_notification

        provider_payment_settings = intent.provider_payment_settings
        family_payment_settings = intent.family_payment_settings

        payment = Payment(
            payment_intent_id=intent.id,
            successful_attempt_id=attempt.id,
            provider_payment_settings_id=provider_payment_settings.id,
            family_payment_settings_id=family_payment_settings.id,
            amount_cents=intent.amount_cents,
            payment_method=attempt.payment_method,
            month_allocation_id=intent.month_allocation_id,
            external_provider_id=intent.provider_external_id,
            external_child_id=intent.child_external_id,
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

        provider_result = Provider.select_by_id(
            cols(
                Provider.ID,
                Provider.FIRST_NAME,
                Provider.LAST_NAME,
                Provider.EMAIL,
                Child.join(Child.ID, Child.FIRST_NAME, Child.LAST_NAME),
            ),
            int(intent.provider_external_id),
        ).execute()
        provider = unwrap_or_abort(provider_result)

        # Send payment notification email to provider
        send_payment_notification(
            provider_name=format_name(provider),
            provider_email=Provider.EMAIL(provider),
            provider_id=intent.provider_external_id,
            child_name=format_name(intent.child),
            child_id=intent.child_external_id,
            amount_cents=intent.amount_cents,
            payment_method=attempt.payment_method.value,
        )
        current_app.logger.info(f"Payment notification sent for Payment {payment.id}")

        return payment

    def _execute_payment_flow(
        self,
        attempt: PaymentAttempt,
        intent: "PaymentIntent",
        provider_payment_settings: "ProviderPaymentSettings",
        family_payment_settings: "FamilyPaymentSettings",
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
            TransferFundsToCardDirection,
            TransferFundsToCardFundingMethod,
            TransferFundsToCardRequest,
        )

        # Get care days and lump sums for metadata
        allocated_care_days = intent.get_care_days()
        allocated_lump_sums = intent.get_lump_sums()

        # Build description and metadata for tracking
        payment_type = " and ".join(self._get_types(allocated_care_days, allocated_lump_sums))
        description = self._generate_description(intent.provider_external_id, allocated_care_days, allocated_lump_sums)

        metadata = {
            "provider_id": intent.provider_external_id,
            "child_id": intent.child_external_id,
            "family_id": family_payment_settings.family_external_id,
            "family_chek_user_id": family_payment_settings.chek_user_id,
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

        # 1. Initiate Chek transfer (Wallet to Wallet)
        transfer_request = TransferBalanceRequest(
            flow_direction=FlowDirection.WALLET_TO_WALLET.value,
            program_id=provider_payment_settings.chek_user_id,  # Documentation says program_id but API uses counterparty_id
            counterparty_id=provider_payment_settings.chek_user_id,  # Set both for safety
            amount=intent.amount_cents,
            description=description,
            metadata=metadata,
        )
        transfer_response = self.chek_service.transfer_balance(
            user_id=int(family_payment_settings.chek_user_id), request=transfer_request
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
                funding_source=ACHFundingSource.WALLET,
                program_id=self.chek_service.program_id,
            )

            ach_response = self.chek_service.send_ach_payment(
                user_id=int(provider_payment_settings.chek_user_id),
                request=ach_request,
            )

            # Record successful ACH payment
            self._update_payment_attempt_facts(attempt, ach_payment_id=ach_response.payment_id)

            current_app.logger.info(
                f"ACH payment initiated for provider {provider_payment_settings.id}. Payment ID: {ach_response.payment_id}, Status: {ach_response.status}"
            )
        else:
            # If Card payment, transfer funds to card
            if not provider_payment_settings.chek_card_id:
                raise PaymentMethodNotConfiguredException("Provider has no card ID for card payment")

            funds_transfer_request = TransferFundsToCardRequest(
                direction=TransferFundsToCardDirection.ALLOCATE_TO_CARD,
                funding_method=TransferFundsToCardFundingMethod.WALLET,
                amount=intent.amount_cents,
            )

            card_transfer_response = self.chek_service.transfer_funds_to_card(
                card_id=provider_payment_settings.chek_card_id,
                request=funds_transfer_request,
            )

            self._update_payment_attempt_facts(attempt, card_transfer_id=str(card_transfer_response.transfer.id))

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
        card_transfer_id: Optional[str] = None,
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
        if card_transfer_id:
            attempt.card_transfer_id = card_transfer_id
            attempt.card_transfer_at = datetime.now(timezone.utc)
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
            # 0. Look up family payment settings
            family_payment_settings = self._get_family_settings_from_child_id(external_child_id)
            if not family_payment_settings or not family_payment_settings.chek_user_id:
                raise ProviderNotPayableException(f"Family for child {external_child_id} does not have chek account")
            if not family_payment_settings.can_make_payments:
                raise ProviderNotPayableException(f"Family for child {external_child_id} cannot make payments")

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

            # 3. Validate payment doesn't exceed $1400 limit
            if amount_cents > MAX_PAYMENT_AMOUNT_CENTS:
                error_msg = (
                    f"Payment amount ${amount_cents / 100:.2f} exceeds maximum allowed payment "
                    f"of ${MAX_PAYMENT_AMOUNT_CENTS / 100:.2f}"
                )
                current_app.logger.error(f"Payment failed for Provider {provider_payment_settings.id}: {error_msg}")
                raise PaymentLimitExceededException(error_msg)

            # 4. Validate payment doesn't exceed remaining allocation
            if amount_cents > month_allocation.remaining_unpaid_cents:
                error_msg = (
                    f"Payment amount {amount_cents} cents exceeds remaining allocation "
                    f"{month_allocation.remaining_unpaid_cents} cents for month {month_allocation.date.strftime('%Y-%m')}"
                )
                current_app.logger.error(f"Payment failed for Provider {provider_payment_settings.id}: {error_msg}")
                raise AllocationExceededException(error_msg)
            if amount_cents > family_payment_settings.chek_wallet_balance:
                error_msg = (
                    f"Payment amount {amount_cents} cents exceeds family Chek wallet balance "
                    f"{family_payment_settings.chek_wallet_balance} cents"
                )
                current_app.logger.error(f"Payment failed for Provider {provider_payment_settings.id}: {error_msg}")
                raise AllocationExceededException(error_msg)

            # 5. Ensure provider has a payment method configured
            if not provider_payment_settings.payment_method:
                error_msg = f"Provider {external_provider_id} has no payment method configured"
                current_app.logger.error(f"Payment failed for Provider {provider_payment_settings.id}: {error_msg}")
                raise PaymentMethodNotConfiguredException(error_msg)

            # 6. Refresh provider Chek status to ensure freshness
            self.refresh_provider_settings(provider_payment_settings)
            db.session.flush()  # Ensure provider object is updated in session

            # 7. Create PaymentIntent to capture what we're trying to pay for
            intent = self._create_payment_intent(
                provider_payment_settings=provider_payment_settings,
                family_payment_settings=family_payment_settings,
                amount_cents=amount_cents,
                month_allocation=month_allocation,
                external_provider_id=external_provider_id,
                external_child_id=external_child_id,
                allocated_care_days=allocated_care_days,
                allocated_lump_sums=allocated_lump_sums,
            )

            # 8. Create PaymentAttempt for this intent
            attempt = self._create_payment_attempt(
                intent=intent,
                payment_method=provider_payment_settings.payment_method,
                provider_payment_settings=provider_payment_settings,
                family_payment_settings=family_payment_settings,
            )

            # 9. Validate payment method status with detailed error messages
            is_valid, validation_error = provider_payment_settings.validate_payment_method_status()
            if not is_valid:
                current_app.logger.warning(
                    f"Payment skipped for Provider {provider_payment_settings.id}: {validation_error}"
                )
                self._update_payment_attempt_facts(attempt, error_message=validation_error)
                db.session.commit()
                return False

            # 10. Execute the payment flow
            try:
                success = self._execute_payment_flow(
                    attempt=attempt,
                    intent=intent,
                    provider_payment_settings=provider_payment_settings,
                    family_payment_settings=family_payment_settings,
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
            family_payment_settings = intent.family_payment_settings

            # Find the latest attempt to determine retry strategy
            last_attempt = intent.latest_attempt

            # Determine if we need full payment or just ACH/Card completion
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
                    provider_payment_settings=provider_payment_settings,
                    family_payment_settings=family_payment_settings,
                )

                # Copy wallet funding info from previous attempt
                new_attempt.wallet_transfer_id = last_attempt.wallet_transfer_id
                new_attempt.wallet_transfer_at = last_attempt.wallet_transfer_at

                try:
                    # Just do the ACH part
                    ach_request = ACHPaymentRequest(
                        amount=intent.amount_cents,
                        type=ACHPaymentType.SAME_DAY_ACH,
                        funding_source=ACHFundingSource.WALLET,
                        program_id=self.chek_service.program_id,
                    )

                    if not provider_payment_settings.chek_direct_pay_id:
                        raise PaymentMethodNotConfiguredException(
                            "Provider has no direct pay account ID for ACH payment"
                        )

                    ach_response = self.chek_service.send_ach_payment(
                        user_id=int(provider_payment_settings.chek_user_id),
                        request=ach_request,
                    )

                    # Record successful ACH
                    self._update_payment_attempt_facts(
                        new_attempt,
                        ach_payment_id=ach_response.payment_id,
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

            elif (
                last_attempt
                and last_attempt.payment_method == PaymentMethod.CARD
                and last_attempt.wallet_transfer_id
                and not last_attempt.card_transfer_id
            ):
                # Wallet funded but card transfer incomplete - just retry card transfer
                current_app.logger.info(f"Retrying card transfer for Intent {intent_id} (wallet already funded)")

                # Create new attempt that continues from the wallet-funded state
                new_attempt = self._create_payment_attempt(
                    intent=intent,
                    payment_method=PaymentMethod.CARD,
                    provider_payment_settings=provider_payment_settings,
                    family_payment_settings=family_payment_settings,
                )

                # Copy wallet funding info from previous attempt
                new_attempt.wallet_transfer_id = last_attempt.wallet_transfer_id
                new_attempt.wallet_transfer_at = last_attempt.wallet_transfer_at

                try:
                    from app.integrations.chek.schemas import (
                        TransferFundsToCardDirection,
                        TransferFundsToCardFundingMethod,
                        TransferFundsToCardRequest,
                    )

                    # Just do the card transfer part
                    if not provider_payment_settings.chek_card_id:
                        raise PaymentMethodNotConfiguredException("Provider has no card ID for card payment")

                    funds_transfer_request = TransferFundsToCardRequest(
                        direction=TransferFundsToCardDirection.ALLOCATE_TO_CARD,
                        funding_method=TransferFundsToCardFundingMethod.WALLET,
                        amount=intent.amount_cents,
                    )

                    card_transfer_response = self.chek_service.transfer_funds_to_card(
                        card_id=provider_payment_settings.chek_card_id,
                        request=funds_transfer_request,
                    )

                    # Record successful card transfer
                    self._update_payment_attempt_facts(
                        new_attempt,
                        card_transfer_id=str(card_transfer_response.transfer.id),
                    )

                    # Create Payment record since now it's complete
                    payment = self._create_payment_on_success(
                        intent=intent,
                        attempt=new_attempt,
                    )

                    db.session.commit()
                    current_app.logger.info(
                        f"Card transfer retry successful for Intent {intent_id}, Payment {payment.id} created"
                    )
                    return True

                except Exception as e:
                    self._update_payment_attempt_facts(new_attempt, error_message=str(e))
                    db.session.commit()
                    current_app.logger.error(f"Card transfer retry failed for Intent {intent_id}: {e}")
                    sentry_sdk.capture_exception(e)
                    return False

            else:
                # Need full payment retry (start from scratch)
                current_app.logger.info(f"Retrying full payment for Intent {intent_id}")

                # Create new attempt
                new_attempt = self._create_payment_attempt(
                    intent=intent,
                    payment_method=provider_payment_settings.payment_method,
                    provider_payment_settings=provider_payment_settings,
                    family_payment_settings=family_payment_settings,
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
                        family_payment_settings=family_payment_settings,
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
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error retrying payment for Intent {intent_id}: {e}")
            sentry_sdk.capture_exception(e)
            return False

    def initialize_provider_payment_method(self, provider_external_id: str, payment_method: str) -> dict:
        """
        Initialize a provider's payment method (card or ACH).

        Args:
            provider_external_id: Provider ID
            payment_method: Either "card" or "ach"

        Returns:
            dict with status and details of the initialization
        """
        from app.integrations.chek.schemas import (
            CardCreateRequest,
            DirectPayAccountInviteRequest,
        )

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
                    amount=1,  # Initial amount in cents
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
                provider_settings.card_initialization_attempted_at = datetime.now(timezone.utc)
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

                provider_result = Provider.select_by_id(cols(Provider.EMAIL), int(provider_external_id)).execute()
                provider = unwrap_or_error(provider_result)

                if provider is None:
                    raise ProviderNotFoundException(f"Provider {provider_external_id} not found")

                provider_email = Provider.EMAIL(provider)
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
                provider_settings.ach_initialization_attempted_at = datetime.now(timezone.utc)
                db.session.commit()

                result["message"] = "ACH invite sent successfully"
                result["invite_response"] = invite_response
                result["invite_sent_to"] = provider_email

            return result

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Failed to initialize payment for provider {provider_external_id}: {e}")
            raise

    def refresh_family_settings(self, family_payment_settings: FamilyPaymentSettings):
        """
        Refreshes the Chek status of a family and updates the database.
        """
        self.family_onboarding.refresh_settings(family_payment_settings)

    def onboard_family(self, family_external_id: str) -> FamilyPaymentSettings:
        """
        Onboards a new family by creating a Chek user and FamilyPaymentSettings record.
        """
        return self.family_onboarding.onboard(family_external_id)

    def refresh_provider_settings(self, provider_payment_settings: ProviderPaymentSettings):
        """
        Refreshes the Chek status of a provider and updates the database.
        """
        self.provider_onboarding.refresh_settings(provider_payment_settings)

    def onboard_provider(self, provider_external_id: str) -> ProviderPaymentSettings:
        """
        Onboards a new provider by creating a Chek user and ProviderPaymentSettings record.
        """
        return self.provider_onboarding.onboard(provider_external_id)

    def _get_family_settings_from_child_id(self, child_external_id: str) -> FamilyPaymentSettings:
        """
        Helper to get FamilyPaymentSettings from a child external ID.
        Raises FamilyNotFoundException if not found.
        """
        child_result = Child.select_by_id(cols(Child.FAMILY_ID), int(child_external_id)).execute()
        child = unwrap_or_error(child_result)

        if child is None:
            raise DataNotFoundException(f"Child {child_external_id} not found")

        family_payment_settings = FamilyPaymentSettings.query.filter_by(
            family_external_id=Child.FAMILY_ID(child)
        ).first()
        if not family_payment_settings:
            return None

        return family_payment_settings

    def allocate_funds_to_family(self, child_external_id: str, amount: int, date: date) -> TransferBalanceResponse:
        """
        Allocates funds to a family's Chek account.
        """
        from app.integrations.chek.schemas import FlowDirection, TransferBalanceRequest

        # If family does not have settings, onboard them
        family_payment_settings = self._get_family_settings_from_child_id(child_external_id)
        if not family_payment_settings or not family_payment_settings.chek_user_id:
            child_result = Child.select_by_id(cols(Child.FAMILY_ID), int(child_external_id)).execute()
            child = unwrap_or_error(child_result)
            if child is None:
                raise DataNotFoundException(f"Child {child_external_id} not found")
            family_payment_settings = self.onboard_family(family_external_id=Child.FAMILY_ID(child))

        # Transfer funds from program to family's wallet
        transfer_request = TransferBalanceRequest(
            flow_direction=FlowDirection.PROGRAM_TO_WALLET.value,
            program_id=self.chek_service.program_id,  # Documentation says program_id but API uses counterparty_id
            counterparty_id=self.chek_service.program_id,  # Set both for safety
            amount=amount,
            description=f"Allocation for child {child_external_id} for month {date.strftime('%Y-%m')}",
            metadata={
                "child_id": child_external_id,
                "family_id": family_payment_settings.family_external_id,
                "allocation_month": date.strftime("%Y-%m"),
            },
        )

        return self.chek_service.transfer_balance(
            user_id=int(family_payment_settings.chek_user_id), request=transfer_request
        )
