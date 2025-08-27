from datetime import datetime, timezone
from typing import Optional

import sentry_sdk
from flask import current_app

from app.config import CARE_DAYS_SAMPLE_SIZE, MAX_PAYMENT_AMOUNT_CENTS
from app.enums.payment_attempt_status import PaymentAttemptStatus
from app.enums.payment_method import PaymentMethod
from app.extensions import db
from app.integrations.chek.schemas import (
    ACHFundingSource,
    ACHPaymentRequest,
    ACHPaymentType,
    FlowDirection,
    TransferBalanceRequest,
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


class PaymentService:
    """
    Service for orchestrating payment processing, including Chek integration,
    database updates, and retry logic.
    """

    def __init__(self, app):
        self.chek_service = ChekIntegrationService(app)
        self.app = app

    def _create_payment_and_attempt(
        self,
        provider: ProviderPaymentSettings,
        amount_cents: int,
        payment_method: PaymentMethod,
        month_allocation: MonthAllocation,
        external_provider_id: str,
        external_child_id: str,
        allocated_care_days: Optional[list[AllocatedCareDay]] = None,
        allocated_lump_sums: Optional[list[AllocatedLumpSum]] = None,
    ) -> Payment:
        """
        Creates a new Payment record and an initial PaymentAttempt.
        """
        payment = Payment(
            provider_id=provider.id,
            chek_user_id=provider.chek_user_id,
            chek_direct_pay_id=provider.chek_direct_pay_id,
            chek_card_id=provider.chek_card_id,
            amount_cents=amount_cents,
            payment_method=payment_method,
            month_allocation=month_allocation,
            external_provider_id=external_provider_id,
            external_child_id=external_child_id,
        )
        db.session.add(payment)
        db.session.flush()  # Assigns an ID to the payment before creating attempt

        # Link care days/lump sums to payment (if provided)
        if allocated_care_days:
            for day in allocated_care_days:
                day.payment = payment
        if allocated_lump_sums:
            for lump_sum in allocated_lump_sums:
                lump_sum.payment = payment

        attempt = PaymentAttempt(
            payment=payment,
            attempt_number=1,
            status=PaymentAttemptStatus.PENDING,
            payment_method=payment_method,
        )
        db.session.add(attempt)
        db.session.flush()

        return payment

    def _update_payment_attempt_status(
        self,
        attempt: PaymentAttempt,
        status: str,
        chek_transfer_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ):
        """
        Updates the status of a PaymentAttempt.
        """
        attempt.status = status
        attempt.chek_transfer_id = chek_transfer_id
        attempt.error_message = error_message
        db.session.add(attempt)

    def process_payment(
        self,
        external_provider_id: str,
        external_child_id: str,
        month_allocation: MonthAllocation,
        allocated_care_days: Optional[list[AllocatedCareDay]] = None,
        allocated_lump_sums: Optional[list[AllocatedLumpSum]] = None,
    ):
        """
        Orchestrates the payment process for a provider.
        Calculates the amount from the allocations and uses the provider's configured payment method.
        """
        try:
            # 1. Look up provider payment settings
            provider = ProviderPaymentSettings.query.filter_by(provider_external_id=external_provider_id).first()
            if not provider:
                error_msg = f"Provider with external ID {external_provider_id} not found in database"
                current_app.logger.error(f"Payment failed: {error_msg}")
                raise ValueError(error_msg)

            # 2. Calculate amount from allocations
            amount_cents = 0
            if allocated_care_days:
                amount_cents += sum(day.amount_cents for day in allocated_care_days)
            if allocated_lump_sums:
                amount_cents += sum(lump.amount_cents for lump in allocated_lump_sums)
            if amount_cents <= 0:
                raise ValueError("No allocations provided for payment")

            # 3. Validate all allocated items are submitted
            if allocated_care_days:
                unsubmitted_days = [day for day in allocated_care_days if day.last_submitted_at is None]
                if unsubmitted_days:
                    error_msg = f"Cannot process payment: {len(unsubmitted_days)} care days are not submitted"
                    current_app.logger.error(f"Payment failed for Provider {provider.id}: {error_msg}")
                    raise ValueError(error_msg)

            if allocated_lump_sums:
                unsubmitted_lumps = [lump for lump in allocated_lump_sums if lump.submitted_at is None]
                if unsubmitted_lumps:
                    error_msg = f"Cannot process payment: {len(unsubmitted_lumps)} lump sums are not submitted"
                    current_app.logger.error(f"Payment failed for Provider {provider.id}: {error_msg}")
                    raise ValueError(error_msg)

            # 4. Validate payment doesn't exceed $1400 limit
            if amount_cents > MAX_PAYMENT_AMOUNT_CENTS:
                error_msg = (
                    f"Payment amount ${amount_cents / 100:.2f} exceeds maximum allowed payment "
                    f"of ${MAX_PAYMENT_AMOUNT_CENTS / 100:.2f}"
                )
                current_app.logger.error(f"Payment failed for Provider {provider.id}: {error_msg}")
                raise ValueError(error_msg)

            # 5. Validate payment doesn't exceed remaining allocation
            if amount_cents > month_allocation.remaining_to_pay_cents:
                error_msg = (
                    f"Payment amount {amount_cents} cents exceeds remaining allocation "
                    f"{month_allocation.remaining_to_pay_cents} cents for month {month_allocation.date.strftime('%Y-%m')}"
                )
                current_app.logger.error(f"Payment failed for Provider {provider.id}: {error_msg}")
                raise ValueError(error_msg)

            # 6. Ensure provider has a payment method configured
            if not provider.payment_method:
                current_app.logger.error(f"Payment failed for Provider {provider.id}: No payment method configured")
                return False

            # 7. Refresh provider Chek status to ensure freshness
            self.refresh_provider_status(provider)
            db.session.flush()  # Ensure provider object is updated in session

            # 8. Check if provider is payable after refresh
            if not provider.payable:
                current_app.logger.warning(f"Payment skipped for Provider {provider.id}: Not payable after refresh.")
                # Create a failed payment record
                payment = self._create_payment_and_attempt(
                    provider=provider,
                    amount_cents=amount_cents,
                    payment_method=provider.payment_method,
                    month_allocation=month_allocation,
                    external_provider_id=external_provider_id,
                    external_child_id=external_child_id,
                    allocated_care_days=allocated_care_days,
                    allocated_lump_sums=allocated_lump_sums,
                )
                self._update_payment_attempt_status(
                    payment.attempts[0], PaymentAttemptStatus.FAILED, error_message="Provider not payable"
                )
                db.session.commit()
                return False

            # 9. Create Payment and initial PaymentAttempt
            payment = self._create_payment_and_attempt(
                provider=provider,
                amount_cents=amount_cents,
                payment_method=provider.payment_method,
                month_allocation=month_allocation,
                external_provider_id=external_provider_id,
                external_child_id=external_child_id,
                allocated_care_days=allocated_care_days,
                allocated_lump_sums=allocated_lump_sums,
            )
            attempt = payment.attempts[0]

            # 10. Initiate Chek transfer (Program to Wallet)
            # Build description and metadata for tracking
            payment_type = "care_days" if allocated_care_days else "lump_sum" if allocated_lump_sums else "other"
            description = f"Payment to provider {external_provider_id} for {payment_type}"

            metadata = {
                "provider_id": external_provider_id,
                "child_id": external_child_id,
                "payment_type": payment_type,
                "payment_id": str(payment.id),
            }

            # Add month/date info based on payment type
            if allocated_care_days and allocated_care_days:
                dates = [
                    day.date.isoformat() for day in allocated_care_days[:CARE_DAYS_SAMPLE_SIZE]
                ]  # First few dates as sample
                metadata["care_dates_sample"] = dates
                metadata["care_days_count"] = len(allocated_care_days)
            elif month_allocation:
                metadata["allocation_month"] = month_allocation.date.strftime("%Y-%m")

            transfer_request = TransferBalanceRequest(
                flow_direction=FlowDirection.PROGRAM_TO_WALLET,
                program_id=self.chek_service.program_id,
                amount=amount_cents,
                description=description,
                metadata=metadata,
            )
            transfer_response = self.chek_service.transfer_balance(
                user_id=int(provider.chek_user_id), request=transfer_request
            )
            # Store transfer ID but don't mark as success yet for ACH payments
            attempt.chek_transfer_id = str(transfer_response.transfer.id)

            # 11. If ACH, initiate ACH payment from wallet to bank account
            if provider.payment_method == PaymentMethod.ACH:
                ach_request = ACHPaymentRequest(
                    amount=amount_cents,
                    type=ACHPaymentType.SAME_DAY_ACH,
                    funding_source=ACHFundingSource.WALLET_BALANCE,
                )
                # Assuming chek_direct_pay_id is available and valid
                if not provider.chek_direct_pay_id:
                    raise ValueError("Provider has no direct pay account ID for ACH payment.")

                ach_response = self.chek_service.send_ach_payment(
                    direct_pay_account_id=int(provider.chek_direct_pay_id), request=ach_request
                )
                # Note: The ACH payment response is the DirectPayAccount object, not a separate transfer ID.
                # We can log this or update the attempt with relevant info if needed.
                current_app.logger.info(
                    f"ACH payment initiated for provider {provider.id}. DirectPayAccount status: {ach_response.status}"
                )

                # Mark as success only after both wallet transfer AND ACH payment complete
                self._update_payment_attempt_status(attempt, PaymentAttemptStatus.SUCCESS)
            else:
                # For virtual card, wallet transfer is the final step
                self._update_payment_attempt_status(attempt, PaymentAttemptStatus.SUCCESS)

            # 12. Mark care days and lump sums as submitted only after successful payment
            # This ensures they are only marked as paid if payment actually succeeded
            if allocated_care_days:
                for day in allocated_care_days:
                    day.mark_as_submitted()
                    day.payment_distribution_requested = True  # Flag to prevent batch script reprocessing

            if allocated_lump_sums:
                for lump_sum in allocated_lump_sums:
                    lump_sum.submitted_at = datetime.now(timezone.utc)
                    lump_sum.paid_at = datetime.now(timezone.utc)

            db.session.commit()
            current_app.logger.info(f"Payment processed successfully for Provider {provider.id}.")
            return True

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error processing payment for Provider {provider.id}: {e}")
            sentry_sdk.capture_exception(e)
            return False

    def retry_ach_payment(self, payment_id: str) -> bool:
        """
        Retry ACH payment for payments where wallet transfer succeeded but ACH failed.
        This handles the specific case where money is in the provider's wallet but ACH didn't complete.
        """
        try:
            payment = Payment.query.get(payment_id)
            if not payment:
                current_app.logger.error(f"Payment {payment_id} not found")
                return False

            provider = ProviderPaymentSettings.query.get(payment.provider_id)
            if not provider:
                current_app.logger.error(f"Provider not found for payment {payment_id}")
                return False

            if provider.payment_method != PaymentMethod.ACH:
                current_app.logger.error(f"Payment {payment_id} is not an ACH payment")
                return False

            # Find the latest attempt that has a transfer ID but failed
            last_attempt = (
                PaymentAttempt.query.filter_by(payment_id=payment.id)
                .filter(PaymentAttempt.chek_transfer_id.isnot(None))
                .filter(PaymentAttempt.status == PaymentAttemptStatus.FAILED)
                .order_by(PaymentAttempt.attempt_number.desc())
                .first()
            )

            if not last_attempt:
                current_app.logger.error(f"No failed attempt with transfer ID found for payment {payment_id}")
                return False

            current_app.logger.info(f"Retrying ACH payment {payment_id} (wallet transfer already completed)")

            # Create new attempt for ACH retry
            next_attempt_number = last_attempt.attempt_number + 1
            new_attempt = PaymentAttempt(
                payment=payment,
                attempt_number=next_attempt_number,
                status=PaymentAttemptStatus.PENDING,
                payment_method=PaymentMethod.ACH,  # This method is specifically for ACH retries
                chek_transfer_id=last_attempt.chek_transfer_id,  # Reuse existing transfer ID
            )
            db.session.add(new_attempt)
            db.session.flush()

            # Refresh provider status
            self.refresh_provider_status(provider)

            if not provider.payable:
                self._update_payment_attempt_status(
                    new_attempt,
                    PaymentAttemptStatus.FAILED,
                    error_message=f"Provider not payable. DirectPay status: {provider.chek_direct_pay_status}",
                )
                db.session.commit()
                return False

            # Retry ACH payment (wallet transfer already completed)
            ach_request = ACHPaymentRequest(
                amount=payment.amount_cents,
                type=ACHPaymentType.SAME_DAY_ACH,
                funding_source=ACHFundingSource.WALLET_BALANCE,
            )

            if not provider.chek_direct_pay_id:
                raise ValueError("Provider has no direct pay account ID for ACH payment")

            ach_response = self.chek_service.send_ach_payment(
                direct_pay_account_id=int(provider.chek_direct_pay_id), request=ach_request
            )

            self._update_payment_attempt_status(new_attempt, PaymentAttemptStatus.SUCCESS)
            db.session.commit()

            current_app.logger.info(f"ACH payment retry successful for {payment_id}")
            return True

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error retrying ACH payment {payment_id}: {e}")
            sentry_sdk.capture_exception(e)
            if "new_attempt" in locals():
                self._update_payment_attempt_status(new_attempt, PaymentAttemptStatus.FAILED, error_message=str(e))
                db.session.commit()
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
            CardDetails,
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
                raise ValueError("Provider has no Chek user ID")

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

                # Create virtual card
                card_request = CardCreateRequest(
                    user_id=int(provider_settings.chek_user_id),
                    card_details=CardDetails(
                        funding_method="wallet",
                        source_id=int(provider_settings.chek_user_id),
                        amount=0,  # Initial amount
                    ),
                )

                card_response = self.chek_service.create_card(card_request)

                # Update provider settings with card info
                provider_settings.chek_card_id = str(card_response.id)
                provider_settings.chek_card_status = "Active"
                provider_settings.payment_method = PaymentMethod.CARD
                provider_settings.payment_method_updated_at = datetime.now(timezone.utc)
                provider_settings.last_chek_sync_at = datetime.now(timezone.utc)
                db.session.commit()

                result["message"] = "Virtual card created successfully"
                result["card_id"] = card_response.id

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
                    raise ValueError(f"Provider {provider_external_id} not found in Google Sheets")

                provider_email = provider_data.get(ProviderColumnNames.EMAIL)
                if not provider_email:
                    raise ValueError(f"Provider {provider_external_id} has no email address")

                # Send ACH invite
                invite_request = DirectPayAccountInviteRequest(
                    user_id=int(provider_settings.chek_user_id), email=provider_email
                )

                invite_response = self.chek_service.invite_direct_pay_account(invite_request)

                # Update provider settings with pending ACH info
                provider_settings.chek_direct_pay_id = str(invite_response.id)
                provider_settings.chek_direct_pay_status = invite_response.status
                provider_settings.payment_method = PaymentMethod.ACH
                provider_settings.payment_method_updated_at = datetime.now(timezone.utc)
                provider_settings.last_chek_sync_at = datetime.now(timezone.utc)
                db.session.commit()

                result["message"] = "ACH invite sent successfully"
                result["direct_pay_id"] = invite_response.id
                result["invite_sent_to"] = provider_email

            return result

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Failed to initialize payment for provider {provider_external_id}: {e}")
            raise

    def refresh_provider_status(self, provider: ProviderPaymentSettings):
        """
        Refreshes the Chek status of a provider and updates the database.
        """
        if not provider.chek_user_id:
            current_app.logger.warning(f"Provider {provider.id} has no chek_user_id. Cannot refresh status.")
            return

        try:
            # Get status from Chek API
            status = self.chek_service.get_provider_chek_status(int(provider.chek_user_id))

            # Update provider with new status
            provider.chek_direct_pay_id = status["direct_pay_id"]
            provider.chek_direct_pay_status = status["direct_pay_status"]
            provider.chek_card_id = status["card_id"]
            provider.chek_card_status = status["card_status"]
            provider.last_chek_sync_at = status["timestamp"]

            db.session.add(provider)
            db.session.commit()
            current_app.logger.info(f"Provider {provider.id} Chek status refreshed successfully.")

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Failed to refresh Chek status for provider {provider.id}: {e}")
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
            existing_provider = ProviderPaymentSettings.query.filter_by(
                provider_external_id=provider_external_id
            ).first()

            if existing_provider:
                current_app.logger.info(
                    f"Provider {provider_external_id} already exists with Chek user {existing_provider.chek_user_id}"
                )
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
            address_line1 = provider_data.get(ProviderColumnNames.ADDRESS_LINE1, "")
            address_line2 = provider_data.get(ProviderColumnNames.ADDRESS_LINE2, "")
            city = provider_data.get(ProviderColumnNames.CITY, "")
            state = provider_data.get(ProviderColumnNames.STATE, "")
            zip_code = provider_data.get(ProviderColumnNames.ZIP_CODE, "")
            country_code = provider_data.get(ProviderColumnNames.COUNTRY_CODE, "US")

            if not provider_email:
                raise ValueError(f"Provider {provider_external_id} has no email in Google Sheets")

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
                    first_name=first_name,
                    last_name=last_name,
                    address=Address(
                        line1=address_line1 or "",
                        line2=address_line2 or "",
                        city=city or "",
                        state=state or "",
                        postal_code=zip_code or "",
                        country=country_code or "US",
                    ),
                )

                chek_user_response = self.chek_service.create_user(user_request)
                current_app.logger.info(
                    f"Created Chek user {chek_user_response.id} for provider {provider_external_id}"
                )
                chek_user_id = str(chek_user_response.id)

            # Create ProviderPaymentSettings record
            provider = ProviderPaymentSettings(
                id=uuid.uuid4(),
                provider_external_id=provider_external_id,
                chek_user_id=chek_user_id,
                payment_method=None,  # Provider chooses this later
            )
            db.session.add(provider)
            db.session.commit()

            current_app.logger.info(
                f"Successfully onboarded provider {provider_external_id} with Chek user {chek_user_id}"
            )
            return provider

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Failed to onboard provider {provider_external_id}: {e}")
            sentry_sdk.capture_exception(e)
            raise
