#!/usr/bin/env python
"""
Script to onboard providers to Chek payment system.

This script finds providers that don't have a Chek user ID in their payment settings
and onboards them by calling the payment service.

Usage:
    python app/scripts/onboard_providers_to_chek.py                      # Onboard all providers missing Chek IDs
    python app/scripts/onboard_providers_to_chek.py --dry-run           # Show what would be processed
    python app/scripts/onboard_providers_to_chek.py --provider-id 123   # Onboard specific provider
    python app/scripts/onboard_providers_to_chek.py --limit 10          # Process only first 10
"""

import argparse
import os
import sys
from typing import Any, Optional

from app.supabase.helpers import cols, unwrap_or_error
from app.supabase.tables import Provider

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from flask import current_app

from app import create_app
from app.models import ProviderPaymentSettings

# Create Flask app context
app = create_app()
app.app_context().push()


def onboard_single_provider(provider_id: str, dry_run: bool) -> Optional[str]:
    """
    Onboard a single provider to Chek.

    Returns:
        None if successful, error message string if failed
    """
    if dry_run:
        print(f"  ✨ {provider_id} - Would onboard to Chek")
        return None

    print(f"  Onboarding {provider_id}...", end=" ")

    try:
        # Call the payment service to onboard the provider
        result = current_app.payment_service.onboard_provider(provider_external_id=provider_id)

        if not result:
            raise RuntimeError("Onboarding failed: no result returned")

        print(f"✅ Chek User ID: {result.chek_user_id if result.chek_user_id else 'Unknown'}")
        return None

    except Exception as e:
        print(f"❌ Failed")
        print(f"    Error: {str(e)}")
        return str(e)


def get_providers_needing_onboarding(
    providers: list, provider_id: Optional[str] = None, limit: Optional[int] = None
) -> list[str]:
    """
    Get list of provider IDs that need Chek onboarding.

    Returns provider IDs that either:
    1. Have payment settings but no chek_user_id, OR
    2. Don't have payment settings at all
    """
    # Get all existing payment settings
    existing_settings = {settings.provider_external_id: settings for settings in ProviderPaymentSettings.query.all()}

    providers_to_onboard = []

    # If specific provider requested
    if provider_id:
        settings = existing_settings.get(provider_id)
        if not settings or not settings.chek_user_id:
            providers_to_onboard.append(provider_id)
    else:
        for provider in providers:
            pid = Provider.ID(provider)

            settings = existing_settings.get(pid)
            # Include if no settings OR settings exist but no chek_user_id
            if not settings or not settings.chek_user_id:
                providers_to_onboard.append(pid)

                if limit and len(providers_to_onboard) >= limit:
                    break

    return providers_to_onboard


def process_providers(
    dry_run: bool = False, provider_id: Optional[str] = None, limit: Optional[int] = None
) -> dict[str, Any]:
    """
    Process providers for Chek onboarding.

    Args:
        dry_run: If True, show what would be processed without actually onboarding
        provider_id: If specified, only process this provider
        limit: If specified, only process this many providers

    Returns:
        Dict with results: processed_count, error_count, etc.
    """
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Processing providers for Chek onboarding")
    print("=" * 60)

    providers_result = Provider.query().select(cols(Provider.ID)).execute()
    providers = unwrap_or_error(providers_result)
    print(f"Found {len(providers)} total providers")

    # Get providers needing onboarding
    providers_to_onboard = get_providers_needing_onboarding(providers, provider_id, limit)

    if not providers_to_onboard:
        if provider_id:
            print(f"✅ Provider {provider_id} already onboarded to Chek")
        else:
            print(f"✅ All providers are already onboarded to Chek")
        return {"status": "success", "processed_count": 0, "error_count": 0, "dry_run": dry_run}

    print(f"\nFound {len(providers_to_onboard)} providers needing Chek onboarding")
    print("-" * 40)

    processed_count = 0
    error_count = 0
    errors = []

    for pid in providers_to_onboard:
        error = onboard_single_provider(pid, dry_run)

        if error:
            error_msg = f"{pid}: {error}"
            errors.append(error_msg)
            error_count += 1
        else:
            processed_count += 1

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"{'DRY RUN ' if dry_run else ''}SUMMARY:")
    print(f"  ✅ {'Would onboard' if dry_run else 'Onboarded'}: {processed_count}")
    print(f"  ❌ Errors: {error_count}")
    print(f"  📊 Total providers processed: {len(providers_to_onboard)}")

    if limit:
        print(f"  ⚠️  Limited to first {limit} providers")

    if errors:
        print(f"\nErrors encountered:")
        for error in errors[:10]:
            print(f"  • {error}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more errors")

    return {
        "status": "success" if error_count == 0 else "completed_with_errors",
        "processed_count": processed_count,
        "error_count": error_count,
        "total_providers": len(providers_to_onboard),
        "errors": errors,
        "dry_run": dry_run,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Onboard providers to Chek payment system.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python app/scripts/onboard_providers_to_chek.py
  python app/scripts/onboard_providers_to_chek.py --dry-run
  python app/scripts/onboard_providers_to_chek.py --provider-id 123
  python app/scripts/onboard_providers_to_chek.py --limit 10
  python app/scripts/onboard_providers_to_chek.py --dry-run --limit 5
        """,
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be processed without actually onboarding"
    )
    parser.add_argument("--provider-id", type=str, help="Onboard specific provider by ID")
    parser.add_argument("--limit", type=int, help="Limit processing to first N providers (useful for testing)")

    args = parser.parse_args()

    try:
        result = process_providers(dry_run=args.dry_run, provider_id=args.provider_id, limit=args.limit)
        sys.exit(0 if result["error_count"] == 0 else 1)

    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
