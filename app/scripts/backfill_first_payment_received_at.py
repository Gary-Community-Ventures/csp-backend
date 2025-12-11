"""
Backfill script to set first_payment_received_at for providers.

This script:
1. Finds all providers in Supabase where first_payment_received_at is null
2. Queries the local PostgreSQL database to find the first successful payment for each provider
3. Updates Supabase with the created_at timestamp from that first payment

Usage:
    python -m app.scripts.backfill_first_payment_received_at [--dry-run]

Options:
    --dry-run    Preview changes without actually updating Supabase
"""

import argparse

from sqlalchemy import func

from app import create_app
from app.models import Payment
from app.supabase.helpers import cols, unwrap_or_error
from app.supabase.tables import Provider


def get_first_payment_per_provider():
    """
    Query the local database to get the first payment (by created_at) for each provider.
    Returns a dict mapping provider_supabase_id -> first payment created_at datetime.
    """
    results = (
        Payment.query.with_entities(
            Payment.provider_supabase_id,
            func.min(Payment.created_at).label("first_payment_at"),
        )
        .filter(Payment.provider_supabase_id.isnot(None))
        .group_by(Payment.provider_supabase_id)
        .all()
    )

    return results


def update_provider_first_payment(provider_id: str, first_payment_at: str):
    """Update a provider's first_payment_received_at in Supabase."""
    Provider.query().update({Provider.FIRST_PAYMENT_RECEIVED_AT: first_payment_at}).eq(Provider.ID, provider_id).is_(
        Provider.FIRST_PAYMENT_RECEIVED_AT, "null"
    ).execute()


def backfill_first_payment_received_at(dry_run: bool = False):
    """Main function to backfill first_payment_received_at for all providers."""
    mode = "DRY RUN" if dry_run else "LIVE"
    app.logger.info(f"[{mode}] Starting backfill of first_payment_received_at...")

    # Get providers that need updating
    result = (
        Provider.query()
        .select(cols(Provider.ID, Provider.NAME, Provider.FIRST_NAME, Provider.LAST_NAME))
        .is_(Provider.FIRST_PAYMENT_RECEIVED_AT, "null")
        .execute()
    )
    providers = unwrap_or_error(result)
    app.logger.info(f"Found {len(providers)} providers without first_payment_received_at set")

    if len(providers) == 0:
        app.logger.info("No providers to update")
        return

    # Get first payment timestamps from local database
    first_payments = get_first_payment_per_provider()
    app.logger.info(f"Found {len(first_payments)} providers with payments in local database")

    # Build set of provider IDs that need updating for quick lookup
    provider_ids_to_update = {Provider.ID(p) for p in providers}

    updated_count = 0
    for row in first_payments:
        if row.provider_supabase_id not in provider_ids_to_update:
            continue

        first_payment_iso = row.first_payment_at.isoformat()

        app.logger.info(
            f"[{mode}] Updating provider {row.provider_supabase_id}: "
            f"first_payment_received_at = {first_payment_iso}"
        )

        if not dry_run:
            update_provider_first_payment(row.provider_supabase_id, first_payment_iso)
        updated_count += 1

    skipped_count = len(providers) - updated_count
    app.logger.info(
        f"[{mode}] Backfill complete: {updated_count} providers updated, {skipped_count} skipped (no payments found)"
    )


if __name__ == "__main__":
    # Create Flask app context
    app = create_app()
    app.app_context().push()

    parser = argparse.ArgumentParser(description="Backfill first_payment_received_at for providers")
    parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="Preview changes without actually updating Supabase",
    )
    args = parser.parse_args()

    backfill_first_payment_received_at(dry_run=args.dry_run)
