from datetime import datetime
from typing import Optional

from flask import current_app
import sentry_sdk

from app.extensions import db
from app.models import ProviderPaymentSettings, Payment, PaymentAttempt, MonthAllocation, AllocatedCareDay, AllocatedLumpSum
from app.integrations.chek.schemas import (
    ACHFundingSource,
    ACHPaymentRequest,
    ACHPaymentType,
    FlowDirection,
    TransferBalanceRequest,
)
from app.integrations.chek.service import ChekService as ChekIntegrationService # Avoid name collision
from app.enums.payment_method import PaymentMethod



class PaymentService:
    """
    Service for orchestrating payment processing, including Chek integration,
    database updates, and retry logic.
    """

    def __init__(self, app):
        self.chek_service = ChekIntegrationService(app)

    def _create_payment_and_attempt(
        self,
        provider: ProviderPaymentSettings,
        amount_cents: int,
        payment_method: PaymentMethod,
        month_allocation: Optional[MonthAllocation] = None,
        allocated_care_days: Optional[list[AllocatedCareDay]] = None,
        allocated_lump_sums: Optional[list[AllocatedLumpSum]] = None,
        external_provider_id: Optional[str] = None,
        external_child_id: Optional[str] = None,
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
            status="pending",
        )
        db.session.add(attempt)
        db.session.flush()

        return payment

    def _update_payment_attempt_status(
        self, attempt: PaymentAttempt, status: str, chek_transfer_id: Optional[str] = None, error_message: Optional[str] = None
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
        provider: ProviderPaymentSettings,
        amount_cents: int,
        payment_method: PaymentMethod,
        month_allocation: Optional[MonthAllocation] = None,
        allocated_care_days: Optional[list[AllocatedCareDay]] = None,
        allocated_lump_sums: Optional[list[AllocatedLumpSum]] = None,
        external_provider_id: Optional[str] = None,
        external_child_id: Optional[str] = None,
    ):
        """
        Orchestrates the payment process for a provider.
        """
        try:
            # 1. Refresh provider Chek status to ensure freshness
            self.chek_service.refresh_provider_status(provider)
            db.session.flush() # Ensure provider object is updated in session

            # 2. Check if provider is payable after refresh
            if not provider.payable:
                current_app.logger.warning(
                    f"Payment skipped for Provider {provider.id}: Not payable after refresh."
                )
                # Create a failed payment record
                payment = self._create_payment_and_attempt(
                    provider=provider,
                    amount_cents=amount_cents,
                    payment_method=payment_method,
                    month_allocation=month_allocation,
                    allocated_care_days=allocated_care_days,
                    allocated_lump_sums=allocated_lump_sums,
                    external_provider_id=external_provider_id,
                    external_child_id=external_child_id,
                )
                self._update_payment_attempt_status(payment.attempts[0], "failed", error_message="Provider not payable")
                db.session.commit()
                return False

            # 3. Create Payment and initial PaymentAttempt
            payment = self._create_payment_and_attempt(
                provider=provider,
                amount_cents=amount_cents,
                payment_method=payment_method,
                month_allocation=month_allocation,
                allocated_care_days=allocated_care_days,
                allocated_lump_sums=allocated_lump_sums,
                external_provider_id=external_provider_id,
                external_child_id=external_child_id,
            )
            attempt = payment.attempts[0]

            # 4. Initiate Chek transfer (Program to Wallet)
            transfer_request = TransferBalanceRequest(
                flow_direction=FlowDirection.PROGRAM_TO_WALLET,
                program_id=self.chek_service.program_id,
                amount=amount_cents,
            )
            transfer_response = self.chek_service.transfer_balance(
                user_id=int(provider.chek_user_id), request=transfer_request
            )
            self._update_payment_attempt_status(
                attempt, "success", chek_transfer_id=str(transfer_response.transfer.id)
            )

            # 5. If ACH, initiate ACH payment from wallet to bank account
            if payment_method == PaymentMethod.ACH:
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
                current_app.logger.info(f"ACH payment initiated for provider {provider.id}. DirectPayAccount status: {ach_response.status}")

            db.session.commit()
            current_app.logger.info(f"Payment processed successfully for Provider {provider.id}.")
            return True

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error processing payment for Provider {provider.id}: {e}")
            sentry_sdk.capture_exception(e)
            return False
