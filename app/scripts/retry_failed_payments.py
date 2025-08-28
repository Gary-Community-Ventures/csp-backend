#!/usr/bin/env python
"""
Manual payment retry script for debugging and retrying failed payments.

Usage:
    python app/scripts/retry_failed_payments.py                    # List all failed payment intents
    python app/scripts/retry_failed_payments.py --intent-id UUID  # Retry specific payment intent
    python app/scripts/retry_failed_payments.py --all             # Retry all failed payment intents
    python app/scripts/retry_failed_payments.py --since DATE      # Retry failures since date
"""

import argparse
import sys
from datetime import datetime, timezone
from uuid import UUID

from app import create_app
from app.extensions import db
from app.models import PaymentIntent, PaymentAttempt, ProviderPaymentSettings
from app.services.payment_service import PaymentService

# Create Flask app context
app = create_app()
app.app_context().push()


def list_failed_payment_intents(since_date=None):
    """List all failed payment intents with details."""
    # Find PaymentIntents that have failed attempts but no successful payment
    query = (
        db.session.query(PaymentIntent)
        .join(PaymentAttempt)
        .filter(
            PaymentAttempt.error_message.isnot(None),  # Has failed attempts
            PaymentIntent.payment.is_(None)  # No successful payment created
        )
    )

    if since_date:
        query = query.filter(PaymentIntent.created_at >= since_date)

    # Get unique failed payment intents
    failed_intents = query.distinct().order_by(PaymentIntent.created_at.desc()).all()

    if not failed_intents:
        print("No failed payment intents found.")
        return []

    print(f"\nFound {len(failed_intents)} failed payment intent(s):\n")
    print("-" * 80)

    for intent in failed_intents:
        provider_payment_settings = intent.provider_payment_settings
        last_attempt = intent.latest_attempt

        print(f"Intent ID: {intent.id}")
        print(f"Provider: {intent.provider_external_id}")
        print(f"Amount: ${intent.amount_cents / 100:.2f}")
        print(f"Created: {intent.created_at}")
        print(f"Status: {intent.status}")
        print(f"Attempts: {len(intent.attempts)}")
        print(f"Last Error: {last_attempt.error_message if last_attempt and last_attempt.error_message else 'N/A'}")
        print("-" * 80)

    return failed_intents


def retry_payment_intent(intent_id):
    """Retry a specific failed payment intent."""
    try:
        intent = PaymentIntent.query.get(intent_id)
        if not intent:
            print(f"Error: Payment Intent {intent_id} not found.")
            return False

        # Check if payment already succeeded
        if intent.payment:
            print(f"Payment Intent {intent_id} has already succeeded. Skipping retry.")
            return True

        print(f"\nRetrying payment intent {intent_id}...")
        print(f"Provider: {intent.provider_external_id}")
        print(f"Amount: ${intent.amount_cents / 100:.2f}")
        print(f"Current status: {intent.status}")

        # Initialize payment service and retry using the new method
        payment_service = PaymentService(app)

        success = payment_service.retry_payment_intent(str(intent_id))
        
        if success:
            print(f"✓ Payment Intent {intent_id} retry successful")
            return True
        else:
            print(f"✗ Payment Intent {intent_id} retry failed")
            return False

    except Exception as e:
        print(f"Error retrying payment intent {intent_id}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Manual payment retry script for debugging and retrying failed payment intents."
    )
    parser.add_argument("--intent-id", type=str, help="UUID of specific payment intent to retry")
    parser.add_argument("--all", action="store_true", help="Retry all failed payment intents")
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

    # List failed payment intents if no specific action requested
    if not args.intent_id and not args.all:
        list_failed_payment_intents(since_date)
        print("\nUse --intent-id UUID to retry a specific payment intent")
        print("Use --all to retry all failed payment intents")
        return

    # Retry specific payment intent
    if args.intent_id:
        try:
            intent_uuid = UUID(args.intent_id)
        except ValueError:
            print(f"Error: Invalid UUID format: {args.intent_id}")
            sys.exit(1)

        if args.dry_run:
            print(f"[DRY RUN] Would retry payment intent {intent_uuid}")
        else:
            success = retry_payment_intent(intent_uuid)
            sys.exit(0 if success else 1)

    # Retry all failed payment intents
    if args.all:
        failed_intents = list_failed_payment_intents(since_date)

        if not failed_intents:
            return

        if args.dry_run:
            print(f"\n[DRY RUN] Would retry {len(failed_intents)} payment intent(s)")
            return

        print(f"\nRetrying {len(failed_intents)} payment intent(s)...")
        confirm = input("Are you sure you want to retry all failed payment intents? (yes/no): ")

        if confirm.lower() != "yes":
            print("Aborted.")
            return

        success_count = 0
        for intent in failed_intents:
            if retry_payment_intent(intent.id):
                success_count += 1

        print(f"\n{success_count}/{len(failed_intents)} payment intents retried successfully.")


if __name__ == "__main__":
    main()
