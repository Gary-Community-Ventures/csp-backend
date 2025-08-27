#!/usr/bin/env python
"""
Manual payment retry script for debugging and retrying failed payments.

Usage:
    python app/scripts/retry_failed_payments.py                    # List all failed payments
    python app/scripts/retry_failed_payments.py --payment-id UUID  # Retry specific payment
    python app/scripts/retry_failed_payments.py --all             # Retry all failed payments
    python app/scripts/retry_failed_payments.py --since DATE      # Retry failures since date
"""

import argparse
import sys
from datetime import datetime, timezone
from uuid import UUID

from app import create_app
from app.enums.payment_attempt_status import PaymentAttemptStatus
from app.enums.payment_method import PaymentMethod
from app.extensions import db
from app.models import Payment, PaymentAttempt, ProviderPaymentSettings
from app.services.payment_service import PaymentService

# Create Flask app context
app = create_app()
app.app_context().push()


def list_failed_payments(since_date=None):
    """List all failed payments with details."""
    query = db.session.query(Payment).join(PaymentAttempt).filter(PaymentAttempt.status == PaymentAttemptStatus.FAILED)

    if since_date:
        query = query.filter(Payment.created_at >= since_date)

    # Get unique failed payments
    failed_payments = query.distinct().order_by(Payment.created_at.desc()).all()

    if not failed_payments:
        print("No failed payments found.")
        return []

    print(f"\nFound {len(failed_payments)} failed payment(s):\n")
    print("-" * 80)

    for payment in failed_payments:
        provider = ProviderPaymentSettings.query.get(payment.provider_id)
        last_attempt = (
            PaymentAttempt.query.filter_by(payment_id=payment.id).order_by(PaymentAttempt.attempt_number.desc()).first()
        )

        print(f"Payment ID: {payment.id}")
        print(f"Provider: {provider.provider_external_id if provider else 'Unknown'}")
        print(f"Amount: ${payment.amount_cents / 100:.2f}")
        print(f"Created: {payment.created_at}")
        print(f"Attempts: {last_attempt.attempt_number if last_attempt else 0}")
        print(f"Last Error: {last_attempt.error_message if last_attempt else 'N/A'}")
        print("-" * 80)

    return failed_payments


def retry_payment(payment_id):
    """Retry a specific failed payment."""
    try:
        payment = Payment.query.get(payment_id)
        if not payment:
            print(f"Error: Payment {payment_id} not found.")
            return False

        provider = ProviderPaymentSettings.query.get(payment.provider_id)
        if not provider:
            print(f"Error: Provider not found for payment {payment_id}.")
            return False

        # Check if payment already succeeded
        successful_attempt = PaymentAttempt.query.filter_by(
            payment_id=payment.id, status=PaymentAttemptStatus.SUCCESS
        ).first()

        if successful_attempt:
            print(f"Payment {payment_id} has already succeeded. Skipping retry.")
            return True

        print(f"\nRetrying payment {payment_id}...")
        print(f"Provider: {provider.provider_external_id}")
        print(f"Amount: ${payment.amount_cents / 100:.2f}")

        # Get the last attempt number
        last_attempt = (
            PaymentAttempt.query.filter_by(payment_id=payment.id).order_by(PaymentAttempt.attempt_number.desc()).first()
        )

        next_attempt_number = (last_attempt.attempt_number + 1) if last_attempt else 1

        # Create new payment attempt
        new_attempt = PaymentAttempt(
            payment_id=payment.id,
            attempt_number=next_attempt_number,
            status=PaymentAttemptStatus.PENDING,
            payment_method=provider.payment_method,  # Use current provider payment method
            attempted_at=datetime.now(timezone.utc),
        )
        db.session.add(new_attempt)
        db.session.flush()

        # Initialize payment service and retry
        payment_service = PaymentService(app)

        try:
            # Refresh provider status first
            payment_service.refresh_provider_status(provider)

            # Check if provider is payable
            if not provider.payable:
                new_attempt.status = PaymentAttemptStatus.FAILED
                new_attempt.error_message = f"Provider not payable. Payment method: {provider.payment_method}, DirectPay status: {provider.chek_direct_pay_status}, Card status: {provider.chek_card_status}"
                db.session.commit()
                print(f"Error: Provider is not in payable state.")
                return False

            # Build transfer request with metadata
            from app.integrations.chek.schemas import (
                FlowDirection,
                TransferBalanceRequest,
            )

            transfer_request = TransferBalanceRequest(
                flow_direction=FlowDirection.PROGRAM_TO_WALLET,
                program_id=payment_service.chek_service.program_id,
                amount=payment.amount_cents,
                description=f"Retry payment {payment_id} to provider {provider.provider_external_id}",
                metadata={
                    "provider_id": payment.external_provider_id,
                    "child_id": payment.external_child_id,
                    "payment_id": str(payment.id),
                    "retry_attempt": next_attempt_number,
                    "original_payment_date": payment.created_at.isoformat(),
                },
            )

            # Process the payment based on payment method
            if provider.payment_method == PaymentMethod.CARD:
                # For virtual card, just do the transfer to wallet
                transfer_response = payment_service.chek_service.transfer_balance(
                    int(provider.chek_user_id), transfer_request
                )

                if transfer_response:
                    new_attempt.status = PaymentAttemptStatus.SUCCESS
                    new_attempt.chek_transfer_id = str(transfer_response.transfer.id)
                    print(f"✓ Payment {payment_id} retry successful (Virtual Card)")
                else:
                    raise Exception("Transfer to wallet failed")

            elif provider.payment_method == PaymentMethod.ACH:
                # For ACH, do transfer then initiate ACH payment
                transfer_response = payment_service.chek_service.transfer_balance(
                    int(provider.chek_user_id), transfer_request
                )

                if not transfer_response:
                    raise Exception("Transfer to wallet failed")

                new_attempt.chek_transfer_id = str(transfer_response.transfer.id)

                # Send ACH payment
                from app.integrations.chek.schemas import (
                    ACHFundingSource,
                    ACHPaymentRequest,
                    ACHPaymentType,
                )

                ach_request = ACHPaymentRequest(
                    amount=payment.amount_cents,
                    type=ACHPaymentType.SAME_DAY_ACH,
                    funding_source=ACHFundingSource.WALLET_BALANCE,
                )

                ach_response = payment_service.chek_service.send_ach_payment(
                    int(provider.chek_direct_pay_id), ach_request
                )

                if ach_response:
                    new_attempt.status = PaymentAttemptStatus.SUCCESS
                    print(f"✓ Payment {payment_id} retry successful (ACH)")
                else:
                    raise Exception("ACH payment initiation failed")
            else:
                raise Exception(f"Unknown payment method: {provider.payment_method}")

            db.session.commit()
            return True

        except Exception as e:
            new_attempt.status = "failed"
            new_attempt.error_message = str(e)
            db.session.commit()
            print(f"✗ Payment {payment_id} retry failed: {e}")
            return False

    except Exception as e:
        db.session.rollback()
        print(f"Error retrying payment {payment_id}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Manual payment retry script for debugging and retrying failed payments."
    )
    parser.add_argument("--payment-id", type=str, help="UUID of specific payment to retry")
    parser.add_argument("--all", action="store_true", help="Retry all failed payments")
    parser.add_argument("--since", type=str, help="Retry failures since date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be retried without actually retrying")

    args = parser.parse_args()

    # Parse since date if provided
    since_date = None
    if args.since:
        try:
            since_date = datetime.strptime(args.since, "%Y-%m-%d")
        except ValueError:
            print(f"Error: Invalid date format. Use YYYY-MM-DD")
            sys.exit(1)

    # List failed payments if no specific action requested
    if not args.payment_id and not args.all:
        list_failed_payments(since_date)
        print("\nUse --payment-id UUID to retry a specific payment")
        print("Use --all to retry all failed payments")
        return

    # Retry specific payment
    if args.payment_id:
        try:
            payment_uuid = UUID(args.payment_id)
        except ValueError:
            print(f"Error: Invalid UUID format: {args.payment_id}")
            sys.exit(1)

        if args.dry_run:
            print(f"[DRY RUN] Would retry payment {payment_uuid}")
        else:
            success = retry_payment(payment_uuid)
            sys.exit(0 if success else 1)

    # Retry all failed payments
    if args.all:
        failed_payments = list_failed_payments(since_date)

        if not failed_payments:
            return

        if args.dry_run:
            print(f"\n[DRY RUN] Would retry {len(failed_payments)} payment(s)")
            return

        print(f"\nRetrying {len(failed_payments)} payment(s)...")
        confirm = input("Are you sure you want to retry all failed payments? (yes/no): ")

        if confirm.lower() != "yes":
            print("Aborted.")
            return

        success_count = 0
        for payment in failed_payments:
            if retry_payment(payment.id):
                success_count += 1

        print(f"\n{success_count}/{len(failed_payments)} payments retried successfully.")


if __name__ == "__main__":
    main()
