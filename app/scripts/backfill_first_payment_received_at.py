"""
Backfill script to set first_payment_received_at for providers and first_payment_sent_at for families.

This script:
1. Finds all providers in Supabase where first_payment_received_at is null
2. Finds all families in Supabase where first_payment_sent_at is null
3. Queries the local PostgreSQL database to find the first successful payment for each
4. Updates Supabase with the created_at timestamp from that first payment

Usage:
    python -m app.scripts.backfill_first_payment_received_at [--dry-run]

Options:
    --dry-run    Preview changes without actually updating Supabase
"""

import argparse

from sqlalchemy import func

from app import create_app
from app.models import Payment
from app.models.family_payment_settings import FamilyPaymentSettings
from app.supabase.helpers import cols, unwrap_or_error
from app.supabase.tables import Family, Provider


def get_first_payment_per_provider():
    """Query the local database to get the first payment (by created_at) for each provider."""
    return (
        Payment.query.with_entities(
            Payment.provider_supabase_id,
            func.min(Payment.created_at).label("first_payment_at"),
        )
        .filter(Payment.provider_supabase_id.isnot(None))
        .group_by(Payment.provider_supabase_id)
        .all()
    )


def get_first_payment_per_family():
    """Query the local database to get the first payment (by created_at) for each family."""
    return (
        Payment.query.with_entities(
            FamilyPaymentSettings.family_supabase_id,
            func.min(Payment.created_at).label("first_payment_at"),
        )
        .join(FamilyPaymentSettings, Payment.family_payment_settings_id == FamilyPaymentSettings.id)
        .filter(FamilyPaymentSettings.family_supabase_id.isnot(None))
        .group_by(FamilyPaymentSettings.family_supabase_id)
        .all()
    )


def backfill_first_payment_received_at(dry_run: bool = False):
    """Main function to backfill first payment timestamps for providers and families."""
    mode = "DRY RUN" if dry_run else "LIVE"
    app.logger.info(f"[{mode}] Starting backfill of first payment timestamps...")

    # Get providers and families that need updating
    providers = unwrap_or_error(
        Provider.query()
        .select(cols(Provider.ID, Provider.NAME, Provider.FIRST_NAME, Provider.LAST_NAME))
        .is_(Provider.FIRST_PAYMENT_RECEIVED_AT, "null")
        .execute()
    )
    families = unwrap_or_error(
        Family.query().select(cols(Family.ID)).is_(Family.FIRST_PAYMENT_SENT_AT, "null").execute()
    )
    app.logger.info(f"Found {len(providers)} providers and {len(families)} families to potentially update")

    if len(providers) == 0 and len(families) == 0:
        app.logger.info("Nothing to update")
        return

    # Get first payment timestamps from local database
    provider_first_payments = get_first_payment_per_provider()
    family_first_payments = get_first_payment_per_family()
    app.logger.info(
        f"Found {len(provider_first_payments)} providers and {len(family_first_payments)} families with payments"
    )

    provider_ids_to_update = {Provider.ID(p) for p in providers}
    family_ids_to_update = {Family.ID(f) for f in families}

    provider_updated = 0
    for row in provider_first_payments:
        if row.provider_supabase_id not in provider_ids_to_update:
            continue
        first_payment_iso = row.first_payment_at.isoformat()
        app.logger.info(
            f"[{mode}] Provider {row.provider_supabase_id}: first_payment_received_at = {first_payment_iso}"
        )
        if not dry_run:
            Provider.query().update({Provider.FIRST_PAYMENT_RECEIVED_AT: first_payment_iso}).eq(
                Provider.ID, row.provider_supabase_id
            ).is_(Provider.FIRST_PAYMENT_RECEIVED_AT, "null").execute()
        provider_updated += 1

    family_updated = 0
    for row in family_first_payments:
        if row.family_supabase_id not in family_ids_to_update:
            continue
        first_payment_iso = row.first_payment_at.isoformat()
        app.logger.info(f"[{mode}] Family {row.family_supabase_id}: first_payment_sent_at = {first_payment_iso}")
        if not dry_run:
            Family.query().update({Family.FIRST_PAYMENT_SENT_AT: first_payment_iso}).eq(
                Family.ID, row.family_supabase_id
            ).is_(Family.FIRST_PAYMENT_SENT_AT, "null").execute()
        family_updated += 1

    app.logger.info(
        f"[{mode}] Backfill complete: {provider_updated} providers updated, {family_updated} families updated"
    )


if __name__ == "__main__":
    app = create_app()
    app.app_context().push()

    parser = argparse.ArgumentParser(description="Backfill first payment timestamps for providers and families")
    parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="Preview changes without actually updating Supabase",
    )
    args = parser.parse_args()

    backfill_first_payment_received_at(dry_run=args.dry_run)
