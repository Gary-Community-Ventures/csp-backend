#!/usr/bin/env python
"""
Script to create Chek transactions for existing monthly allocations that are missing transfer IDs.

This script finds all monthly allocations from September 2025 onwards that don't have a
chek_transfer_id and creates the transfer by calling the payment service.

Usage:
    python app/scripts/create_transactions_for_allocations.py                    # Process all missing transfers
    python app/scripts/create_transactions_for_allocations.py --dry-run         # Show what would be processed
    python app/scripts/create_transactions_for_allocations.py --limit 10        # Process only first 10
"""

import argparse
import os
import sys
from datetime import date, datetime
from typing import Any, Dict, List

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from flask import current_app
from sqlalchemy import and_

from app import create_app
from app.extensions import db
from app.models.month_allocation import MonthAllocation
from app.sheets.mappings import ChildColumnNames, get_child, get_children

# Create Flask app context
app = create_app()
app.app_context().push()


def process_missing_allocations(dry_run: bool = False, limit: int = None) -> Dict[str, Any]:
    """
    Process all monthly allocations that are missing transfer IDs.

    Args:
        dry_run: If True, show what would be processed without actually creating transfers
        limit: If specified, only process this many allocations (useful for testing)

    Returns:
        Dict with results: processed_count, error_count, etc.
    """
    try:
        print(f"\n{'[DRY RUN] ' if dry_run else ''}Processing allocations missing transfer IDs")
        print("=" * 60)

        # Get all children data for reference
        try:
            all_children = get_children()
        except Exception as e:
            print(f"❌ Failed to fetch children from Google Sheets: {e}")
            raise

        # Define the cutoff date - September 2025
        cutoff_date = date(2025, 9, 1)

        # Query all allocations that are missing transfer IDs from September 2025 onwards
        query = MonthAllocation.query.filter(
            and_(MonthAllocation.date >= cutoff_date, MonthAllocation.chek_transfer_id.is_(None))
        ).order_by(MonthAllocation.date, MonthAllocation.google_sheets_child_id)

        if limit:
            query = query.limit(limit)

        allocations = query.all()

        if not allocations:
            print(f"✅ No allocations missing transfer IDs from {cutoff_date.strftime('%B %Y')} onwards")
            return {"status": "success", "processed_count": 0, "error_count": 0, "dry_run": dry_run}

        # Group allocations by month for better output
        allocations_by_month = {}
        for allocation in allocations:
            month_key = allocation.date.strftime("%Y-%m")
            if month_key not in allocations_by_month:
                allocations_by_month[month_key] = []
            allocations_by_month[month_key].append(allocation)

        print(f"Found {len(allocations)} allocations missing transfer IDs across {len(allocations_by_month)} months")
        print(f"Months affected: {', '.join(sorted(allocations_by_month.keys()))}\n")

        processed_count = 0
        error_count = 0
        errors = []

        # Process allocations month by month for clearer output
        for month_key in sorted(allocations_by_month.keys()):
            month_allocations = allocations_by_month[month_key]
            month_date = datetime.strptime(month_key, "%Y-%m").date()

            print(f"\n📅 Processing {month_date.strftime('%B %Y')} ({len(month_allocations)} allocations)")
            print("-" * 40)

            for allocation in month_allocations:
                child_id = allocation.google_sheets_child_id

                # Get child details for logging
                child_data = get_child(child_id, all_children)
                if child_data:
                    child_name = (
                        f"{child_data.get(ChildColumnNames.FIRST_NAME)} {child_data.get(ChildColumnNames.LAST_NAME)}"
                    )
                else:
                    child_name = "Unknown"

                try:
                    if dry_run:
                        # In dry run, just show what would be processed
                        print(
                            f"  ✨ {child_name} ({child_id}) - Would create transfer for ${allocation.allocation_cents / 100:.2f}"
                        )
                        processed_count += 1
                    else:
                        # Create the transfer using the payment service
                        print(
                            f"  Processing {child_name} ({child_id}) - ${allocation.allocation_cents / 100:.2f}...",
                            end=" ",
                        )

                        transaction = current_app.payment_service.allocate_funds_to_family(
                            child_external_id=child_id, amount=allocation.allocation_cents, date=allocation.date
                        )

                        if not transaction or not transaction.transfer or not transaction.transfer.id:
                            raise RuntimeError(
                                f"Failed to allocate funds to family for child {child_id}: {transaction}"
                            )

                        # Update the allocation with the transfer details
                        allocation.chek_transfer_id = transaction.transfer.id
                        allocation.chek_transfer_date = transaction.transfer.created
                        db.session.add(allocation)

                        print(f"✅ Transfer: {transaction.transfer.id}")
                        processed_count += 1

                except Exception as e:
                    print(f"❌ Failed")
                    error_msg = f"{month_date.strftime('%B %Y')} - {child_name} ({child_id}): {str(e)}"
                    print(f"    Error: {str(e)}")
                    error_count += 1
                    errors.append(error_msg)
                    continue

        # Commit all successful updates (unless dry run)
        if not dry_run and processed_count > 0:
            try:
                db.session.commit()
                print(f"\n✅ Successfully committed {processed_count} transfer updates to database")
            except Exception as e:
                db.session.rollback()
                print(f"\n❌ Failed to commit transfer updates: {e}")
                raise

        result = {
            "status": "success" if error_count == 0 else "completed_with_errors",
            "processed_count": processed_count,
            "error_count": error_count,
            "total_allocations": len(allocations),
            "months_affected": len(allocations_by_month),
            "errors": errors,
            "dry_run": dry_run,
        }

        # Print summary
        print(f"\n{'=' * 60}")
        print(f"{'DRY RUN ' if dry_run else ''}SUMMARY:")
        print(f"  ✅ {'Would process' if dry_run else 'Processed'}: {processed_count}")
        print(f"  ❌ Errors: {error_count}")
        print(f"  📊 Total allocations: {len(allocations)}")
        print(f"  📅 Months affected: {len(allocations_by_month)}")

        if limit:
            print(f"  ⚠️  Limited to first {limit} allocations")

        if errors and error_count > 0:
            print(f"\nErrors encountered:")
            for error in errors[:10]:
                print(f"  • {error}")
            if len(errors) > 10:
                print(f"  ... and {len(errors) - 10} more errors")

        return result

    except Exception as e:
        print(f"\n❌ Failed to process allocations: {str(e)}")
        if not dry_run:
            db.session.rollback()
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Create Chek transactions for monthly allocations missing transfer IDs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python app/scripts/create_transactions_for_allocations.py
  python app/scripts/create_transactions_for_allocations.py --dry-run
  python app/scripts/create_transactions_for_allocations.py --limit 10
  python app/scripts/create_transactions_for_allocations.py --dry-run --limit 5
        """,
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be processed without actually creating transfers"
    )
    parser.add_argument("--limit", type=int, help="Limit processing to first N allocations (useful for testing)")

    args = parser.parse_args()

    try:
        result = process_missing_allocations(dry_run=args.dry_run, limit=args.limit)
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
