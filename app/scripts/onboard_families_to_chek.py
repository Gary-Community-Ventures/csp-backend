#!/usr/bin/env python
"""
Script to onboard families to Chek payment system.

This script finds families that don't have a Chek user ID in their payment settings
and onboards them by calling the payment service.

Usage:
    python app/scripts/onboard_families_to_chek.py                    # Onboard all families missing Chek IDs
    python app/scripts/onboard_families_to_chek.py --dry-run         # Show what would be processed
    python app/scripts/onboard_families_to_chek.py --family-id 123   # Onboard specific family
    python app/scripts/onboard_families_to_chek.py --limit 10        # Process only first 10
"""

import argparse
import os
import sys
from typing import Any, Dict, List, Optional

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from flask import current_app

from app import create_app
from app.models import FamilyPaymentSettings
from app.sheets.mappings import FamilyColumnNames, get_families

# Create Flask app context
app = create_app()
app.app_context().push()


def onboard_single_family(family_id: str, dry_run: bool) -> Optional[str]:
    """
    Onboard a single family to Chek.

    Returns:
        None if successful, error message string if failed
    """
    if dry_run:
        print(f"  ✨ {family_id} - Would onboard to Chek")
        return None

    print(f"  Onboarding {family_id}...", end=" ")

    try:
        # Call the payment service to onboard the family
        result = current_app.payment_service.onboard_family(family_external_id=family_id)

        if not result:
            raise RuntimeError("Onboarding failed: no result returned")

        print(f"✅ Chek User ID: {result.chek_user_id if result.chek_user_id else 'Unknown'}")
        return None

    except Exception as e:
        print(f"❌ Failed")
        print(f"    Error: {str(e)}")
        return str(e)


def get_families_needing_onboarding(
    all_families: List, family_id: Optional[str] = None, limit: Optional[int] = None
) -> List[str]:
    """
    Get list of family IDs that need Chek onboarding.

    Returns family IDs that either:
    1. Have payment settings but no chek_user_id, OR
    2. Don't have payment settings at all
    """
    # Get all existing payment settings
    existing_settings = {settings.family_external_id: settings for settings in FamilyPaymentSettings.query.all()}

    families_to_onboard = []

    # If specific family requested
    if family_id:
        settings = existing_settings.get(family_id)
        if not settings or not settings.chek_user_id:
            families_to_onboard.append(family_id)
    else:
        # Check all families from Google Sheets
        for family_data in all_families:
            fid = family_data.get(FamilyColumnNames.ID)
            if not fid:
                continue

            settings = existing_settings.get(fid)
            # Include if no settings OR settings exist but no chek_user_id
            if not settings or not settings.chek_user_id:
                families_to_onboard.append(fid)

                if limit and len(families_to_onboard) >= limit:
                    break

    return families_to_onboard


def process_families(
    dry_run: bool = False, family_id: Optional[str] = None, limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    Process families for Chek onboarding.

    Args:
        dry_run: If True, show what would be processed without actually onboarding
        family_id: If specified, only process this family
        limit: If specified, only process this many families

    Returns:
        Dict with results: processed_count, error_count, etc.
    """
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Processing families for Chek onboarding")
    print("=" * 60)

    # Get all family data from Google Sheets
    try:
        all_families = get_families()
        print(f"Found {len(all_families)} total families in Google Sheets")
    except Exception as e:
        print(f"❌ Failed to fetch families from Google Sheets: {e}")
        raise

    # Get families needing onboarding
    families_to_onboard = get_families_needing_onboarding(all_families, family_id, limit)

    if not families_to_onboard:
        if family_id:
            print(f"✅ Family {family_id} already onboarded to Chek")
        else:
            print(f"✅ All families are already onboarded to Chek")
        return {"status": "success", "processed_count": 0, "error_count": 0, "dry_run": dry_run}

    print(f"\nFound {len(families_to_onboard)} families needing Chek onboarding")
    print("-" * 40)

    processed_count = 0
    error_count = 0
    errors = []

    for fid in families_to_onboard:
        error = onboard_single_family(fid, dry_run)

        if error:
            error_msg = f"{fid}: {error}"
            errors.append(error_msg)
            error_count += 1
        else:
            processed_count += 1

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"{'DRY RUN ' if dry_run else ''}SUMMARY:")
    print(f"  ✅ {'Would onboard' if dry_run else 'Onboarded'}: {processed_count}")
    print(f"  ❌ Errors: {error_count}")
    print(f"  📊 Total families processed: {len(families_to_onboard)}")

    if limit:
        print(f"  ⚠️  Limited to first {limit} families")

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
        "total_families": len(families_to_onboard),
        "errors": errors,
        "dry_run": dry_run,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Onboard families to Chek payment system.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python app/scripts/onboard_families_to_chek.py
  python app/scripts/onboard_families_to_chek.py --dry-run
  python app/scripts/onboard_families_to_chek.py --family-id family123
  python app/scripts/onboard_families_to_chek.py --limit 10
  python app/scripts/onboard_families_to_chek.py --dry-run --limit 5
        """,
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be processed without actually onboarding"
    )
    parser.add_argument("--family-id", type=str, help="Onboard specific family by ID")
    parser.add_argument("--limit", type=int, help="Limit processing to first N families (useful for testing)")

    args = parser.parse_args()

    try:
        result = process_families(dry_run=args.dry_run, family_id=args.family_id, limit=args.limit)
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
