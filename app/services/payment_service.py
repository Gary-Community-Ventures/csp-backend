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
            # Build description and metadata for tracking
            payment_type = "care_days" if allocated_care_days else "lump_sum" if allocated_lump_sums else "other"
            description = f"Payment to provider {external_provider_id or provider.provider_external_id} for {payment_type}"
            
            metadata = {
                "provider_id": external_provider_id or provider.provider_external_id,
                "child_id": external_child_id,
                "payment_type": payment_type,
                "payment_id": str(payment.id),
            }
            
            # Add month/date info based on payment type
            if allocated_care_days and allocated_care_days:
                dates = [day.date.isoformat() for day in allocated_care_days[:3]]  # First 3 dates as sample
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
            DirectPayAccountInviteRequest
        )
        from app.sheets.mappings import get_providers, get_provider, ProviderColumnNames
        
        try:
            # Ensure provider is onboarded to Chek
            provider_settings = ProviderPaymentSettings.query.filter_by(
                provider_external_id=provider_external_id
            ).first()
            
            if not provider_settings:
                # Onboard the provider to Chek
                provider_settings = self.chek_service.onboard_provider(
                    provider_external_id=provider_external_id
                )
                current_app.logger.info(f"Onboarded provider {provider_external_id} to Chek")
            
            if not provider_settings.chek_user_id:
                raise ValueError("Provider has no Chek user ID")
            
            result = {
                "provider_id": provider_external_id,
                "chek_user_id": provider_settings.chek_user_id,
                "payment_method": payment_method
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
                        amount=0  # Initial amount
                    )
                )
                
                card_response = self.chek_service.create_card(card_request)
                
                # Update provider settings with card info
                provider_settings.chek_card_id = str(card_response.id)
                provider_settings.chek_card_status = "Active"
                provider_settings.payment_method = PaymentMethod.VIRTUAL_CARD
                provider_settings.payment_method_updated_at = datetime.utcnow()
                provider_settings.last_chek_sync_at = datetime.utcnow()
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
                    user_id=int(provider_settings.chek_user_id),
                    email=provider_email
                )
                
                invite_response = self.chek_service.invite_direct_pay_account(invite_request)
                
                # Update provider settings with pending ACH info
                provider_settings.chek_direct_pay_id = str(invite_response.id)
                provider_settings.chek_direct_pay_status = invite_response.status
                provider_settings.payment_method = PaymentMethod.ACH
                provider_settings.payment_method_updated_at = datetime.utcnow()
                provider_settings.last_chek_sync_at = datetime.utcnow()
                db.session.commit()
                
                result["message"] = "ACH invite sent successfully"
                result["direct_pay_id"] = invite_response.id
                result["invite_sent_to"] = provider_email
            
            return result
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Failed to initialize payment for provider {provider_external_id}: {e}")
            raise
