#!/usr/bin/env python
"""
Manual payment retry script for debugging and retrying failed payments.

Usage:
    python app/scripts/retry_failed_payments.py                    # List all failed payment intents
    python app/scripts/retry_failed_payments.py --intent-id UUID  # Retry specific payment intent
    python app/scripts/retry_failed_payments.py --all             # Retry all failed payment intents
    python app/scripts/retry_failed_payments.py --since DATE      # Retry failures since date
"""

import os
import sys


# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import argparse

from datetime import datetime
from uuid import UUID

from app import create_app
from app.extensions import db
from app.models import PaymentAttempt, PaymentIntent
from app.services.payment.payment_service import PaymentService

# Create Flask app context
app = create_app()
app.app_context().push()


def list_failed_payment_intents(since_date=None):
    """List all failed payment intents with details."""
    # Import Payment model
    from app.models import Payment
    
    # Find PaymentIntents that have failed attempts but no successful payment
    # First get the IDs to avoid DISTINCT on JSON columns
    subquery = (
        db.session.query(PaymentIntent.id)
        .join(PaymentAttempt)
        .outerjoin(Payment, PaymentIntent.id == Payment.payment_intent_id)
        .filter(
            PaymentAttempt.error_message.isnot(None),  # Has failed attempts
            Payment.id.is_(None),  # No successful payment created
        )
    )

    if since_date:
        subquery = subquery.filter(PaymentIntent.created_at >= since_date)

    # Get unique intent IDs
    intent_ids = [row[0] for row in subquery.distinct().all()]
    
    # Now fetch the full PaymentIntent objects
    failed_intents = (
        db.session.query(PaymentIntent)
        .filter(PaymentIntent.id.in_(intent_ids))
        .order_by(PaymentIntent.created_at.desc())
        .all()
    ) if intent_ids else []

    if not failed_intents:
        app.logger.info("No failed payment intents found.")
        return []

    app.logger.info(f"Found {len(failed_intents)} failed payment intent(s):")
    app.logger.info("-" * 80)

    for intent in failed_intents:
        last_attempt = intent.latest_attempt

        app.logger.info(f"Intent ID: {intent.id}")
        app.logger.info(f"Provider: {intent.provider_external_id}")
        app.logger.info(f"Amount: ${intent.amount_cents / 100:.2f}")
        app.logger.info(f"Created: {intent.created_at}")
        app.logger.info(f"Status: {intent.status}")
        app.logger.info(f"Attempts: {len(intent.attempts)}")
        app.logger.info(f"Last Error: {last_attempt.error_message if last_attempt and last_attempt.error_message else 'N/A'}")
        app.logger.info("-" * 80)

    return failed_intents


def retry_payment_intent(intent_id):
    """Retry a specific failed payment intent."""
    try:
        intent = PaymentIntent.query.get(intent_id)
        if not intent:
            app.logger.info(f"Error: Payment Intent {intent_id} not found.")
            return False

        # Check if payment already succeeded
        if intent.payment:
            app.logger.info(f"Payment Intent {intent_id} has already succeeded. Skipping retry.")
            return True

        app.logger.info(f"\nRetrying payment intent {intent_id}...")
        app.logger.info(f"Provider: {intent.provider_external_id}")
        app.logger.info(f"Amount: ${intent.amount_cents / 100:.2f}")
        app.logger.info(f"Current status: {intent.status}")

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
