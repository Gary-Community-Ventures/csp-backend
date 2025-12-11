#!/usr/bin/env python
"""
Manual script to reclaim unused funds from monthly allocations.

Usage:
    python app/scripts/reclaim_unused_allocation_funds.py                    # Reclaim from all past months
    python app/scripts/reclaim_unused_allocation_funds.py --month 2024-08   # Reclaim from specific month
    python app/scripts/reclaim_unused_allocation_funds.py --dry-run         # Show what would be reclaimed
"""

import argparse
import os
import sys
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app import create_app
from app.jobs.reclaim_unused_allocation_funds import (
    reclaim_funds_for_month,
    reclaim_past_month_funds,
)

# Create Flask app context
app = create_app()
app.app_context().push()


def reclaim_all_past_months(dry_run: bool = False) -> dict:
    """
    Reclaim unused funds from all past month allocations.

    Args:
        dry_run: If True, show what would be reclaimed without actually reclaiming

    Returns:
        Dict with results
    """
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Reclaiming funds from all past month allocations")
    print("-" * 60)

    # Call the job function directly (not using .delay() for manual execution)
    result = reclaim_past_month_funds(dry_run=dry_run, from_info="manual_script")

    # Print detailed results
    print(f"\n{'=' * 60}")
    print(f"{'DRY RUN ' if dry_run else ''}SUMMARY:")
    print(f"  📅 Current month: {result.get('current_month', 'N/A')}")
    print(f"  📅 Previous month: {result.get('previous_month', 'N/A')}")
    print(f"  📅 Reclaiming from months before: {result.get('reclaimed_from_months_before', 'N/A')}")
    print(f"  🔍 Allocations checked: {result.get('checked_count', 0)}")
    print(f"  ✨ Eligible for reclamation: {result.get('eligible_count', 0)}")
    print(
        f"  {'💰 Would reclaim from' if dry_run else '✅ Reclaimed from'}: {result.get('reclaimed_count', 0)} allocations"
    )
    print(f"  💵 Total amount: ${result.get('total_amount_dollars', 0):.2f}")
    print(f"  ❌ Errors: {result.get('error_count', 0)}")

    if result.get("errors") and result.get("error_count", 0) > 0:
        print(f"\n⚠️  Errors encountered:")
        for error in result["errors"]:
            print(f"  • {error}")

    return result


def reclaim_specific_month(target_month: str, dry_run: bool = False) -> dict:
    """
    Reclaim unused funds from allocations for a specific month.

    Args:
        target_month: Month to reclaim from in YYYY-MM format (e.g., "2024-08")
        dry_run: If True, show what would be reclaimed without actually reclaiming

    Returns:
        Dict with results
    """
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Reclaiming funds from {target_month} allocations")
    print("-" * 60)

    # Call the job function directly (not using .delay() for manual execution)
    result = reclaim_funds_for_month(target_month=target_month, dry_run=dry_run, from_info="manual_script")

    # Print detailed results
    print(f"\n{'=' * 60}")
    print(f"{'DRY RUN ' if dry_run else ''}SUMMARY for {result.get('target_month', target_month)}:")
    print(f"  🔍 Allocations checked: {result.get('checked_count', 0)}")
    print(f"  ✨ Eligible for reclamation: {result.get('eligible_count', 0)}")
    print(
        f"  {'💰 Would reclaim from' if dry_run else '✅ Reclaimed from'}: {result.get('reclaimed_count', 0)} allocations"
    )
    print(f"  💵 Total amount: ${result.get('total_amount_dollars', 0):.2f}")
    print(f"  ❌ Errors: {result.get('error_count', 0)}")

    if result.get("errors") and result.get("error_count", 0) > 0:
        print(f"\n⚠️  Errors encountered:")
        for error in result["errors"]:
            print(f"  • {error}")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Reclaim unused funds from monthly allocations.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Reclaim from all past months (dry run)
  python app/scripts/reclaim_unused_allocation_funds.py --dry-run

  # Actually reclaim from all past months
  python app/scripts/reclaim_unused_allocation_funds.py

  # Reclaim from specific month
  python app/scripts/reclaim_unused_allocation_funds.py --month 2024-08

  # Dry run for specific month
  python app/scripts/reclaim_unused_allocation_funds.py --month 2024-08 --dry-run
        """,
    )
    parser.add_argument("--month", type=str, help="Reclaim from specific month (YYYY-MM format, e.g., 2024-08)")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be reclaimed without actually reclaiming"
    )

    args = parser.parse_args()

    try:
        if args.month:
            # Validate month format
            try:
                datetime.strptime(args.month, "%Y-%m")
            except ValueError:
                print(f"❌ Invalid month format: {args.month}. Use YYYY-MM (e.g., 2024-08)")
                sys.exit(1)

            # Confirm if not dry run
            if not args.dry_run:
                print(f"\n⚠️  You are about to reclaim unused funds from {args.month} allocations.")
                confirm = input("Are you sure you want to continue? (yes/no): ")
                if confirm.lower() != "yes":
                    print("Aborted.")
                    sys.exit(0)

            result = reclaim_specific_month(args.month, args.dry_run)
        else:
            # Default: reclaim from all past months
            if not args.dry_run:
                print("\n⚠️  You are about to reclaim unused funds from ALL past month allocations.")
                confirm = input("Are you sure you want to continue? (yes/no): ")
                if confirm.lower() != "yes":
                    print("Aborted.")
                    sys.exit(0)

            result = reclaim_all_past_months(args.dry_run)

        # Exit with success if no errors, otherwise exit with failure
        status = result.get("status", "success")
        error_count = result.get("error_count", 0)
        sys.exit(0 if error_count == 0 and status == "success" else 1)

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
