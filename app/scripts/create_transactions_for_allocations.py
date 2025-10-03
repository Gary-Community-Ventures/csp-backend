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
from typing import Any, Optional

from app.supabase.helpers import cols, format_name, unwrap_or_error
from app.supabase.tables import Child

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from flask import current_app
from sqlalchemy import and_

from app import create_app
from app.extensions import db
from app.models.month_allocation import MonthAllocation

# Create Flask app context
app = create_app()
app.app_context().push()


def process_single_allocation(allocation: MonthAllocation, child_name: str, dry_run: bool) -> Optional[str]:
    """
    Process a single allocation to create its transfer.

    Returns:
        None if successful, error message string if failed
    """
    child_id = allocation.child_supabase_id
    amount_str = f"${allocation.allocation_cents / 100:.2f}"

    if dry_run:
        print(f"  ✨ {child_name} ({child_id}) - Would create transfer for {amount_str}")
        return None

    print(f"  Processing {child_name} ({child_id}) - {amount_str}...", end=" ")

    try:
        transaction = current_app.payment_service.allocate_funds_to_family(
            child_id=child_id, amount=allocation.allocation_cents, date=allocation.date
        )

        if not transaction or not transaction.transfer or not transaction.transfer.id:
            raise RuntimeError(f"Failed to allocate funds: invalid transaction response")

        # Update the allocation with the transfer details
        allocation.chek_transfer_id = transaction.transfer.id
        allocation.chek_transfer_date = transaction.transfer.created
        db.session.add(allocation)

        print(f"✅ Transfer: {transaction.transfer.id}")
        return None

    except Exception as e:
        print(f"❌ Failed")
        print(f"    Error: {str(e)}")
        return str(e)


def group_allocations_by_month(allocations: list[MonthAllocation]) -> dict[str, list[MonthAllocation]]:
    """Group allocations by month for organized processing."""
    allocations_by_month = {}
    for allocation in allocations:
        month_key = allocation.date.strftime("%Y-%m")
        if month_key not in allocations_by_month:
            allocations_by_month[month_key] = []
        allocations_by_month[month_key].append(allocation)
    return allocations_by_month


def process_month_allocations(
    month_key: str, month_allocations: list[MonthAllocation], children: list, dry_run: bool
) -> tuple[int, list[str]]:
    """
    Process all allocations for a specific month.

    Returns:
        Tuple of (processed_count, error_messages)
    """
    month_date = datetime.strptime(month_key, "%Y-%m").date()
    print(f"\n📅 Processing {month_date.strftime('%B %Y')} ({len(month_allocations)} allocations)")
    print("-" * 40)

    processed_count = 0
    errors = []

    for allocation in month_allocations:
        child_id = allocation.child_supabase_id
        child = Child.find_by_id(children, child_id)
        child_name = format_name(child)

        error = process_single_allocation(allocation, child_name, dry_run)

        if error:
            error_msg = f"{month_date.strftime('%B %Y')} - {child_name} ({child_id}): {error}"
            errors.append(error_msg)
        else:
            processed_count += 1

    return processed_count, errors


def fetch_missing_allocations(cutoff_date: date, limit: Optional[int] = None) -> list[MonthAllocation]:
    """Fetch all allocations missing transfer IDs from the cutoff date."""
    query = MonthAllocation.query.filter(
        and_(
            MonthAllocation.date >= cutoff_date,
            MonthAllocation.chek_transfer_id.is_(None),
            MonthAllocation.allocation_cents > 0,
        )
    ).order_by(MonthAllocation.date, MonthAllocation.child_supabase_id)

    if limit:
        query = query.limit(limit)

    return query.all()


def commit_changes(processed_count: int, dry_run: bool) -> None:
    """Commit database changes if not in dry run mode."""
    if dry_run or processed_count == 0:
        return

    try:
        db.session.commit()
        print(f"\n✅ Successfully committed {processed_count} transfer updates to database")
    except Exception as e:
        db.session.rollback()
        print(f"\n❌ Failed to commit transfer updates: {e}")
        raise


def print_summary(result: dict[str, Any]) -> None:
    """Print the processing summary."""
    dry_run = result["dry_run"]
    print(f"\n{'=' * 60}")
    print(f"{'DRY RUN ' if dry_run else ''}SUMMARY:")
    print(f"  ✅ {'Would process' if dry_run else 'Processed'}: {result['processed_count']}")
    print(f"  ❌ Errors: {result['error_count']}")
    print(f"  📊 Total allocations: {result['total_allocations']}")
    print(f"  📅 Months affected: {result['months_affected']}")

    if result.get("limit"):
        print(f"  ⚠️  Limited to first {result['limit']} allocations")

    errors = result.get("errors", [])
    if errors:
        print(f"\nErrors encountered:")
        for error in errors[:10]:
            print(f"  • {error}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more errors")


def process_missing_allocations(dry_run: bool = False, limit: Optional[int] = None) -> dict[str, Any]:
    """
    Process all monthly allocations that are missing transfer IDs.

    Args:
        dry_run: If True, show what would be processed without actually creating transfers
        limit: If specified, only process this many allocations (useful for testing)

    Returns:
        Dict with results: processed_count, error_count, etc.
    """
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Processing allocations missing transfer IDs")
    print("=" * 60)

    children_result = Child.query().select(cols(Child.ID, Child.FIRST_NAME, Child.LAST_NAME)).execute()
    children = unwrap_or_error(children_result)

    # Define the cutoff date - September 2025
    cutoff_date = date(2025, 9, 1)

    # Fetch allocations
    allocations = fetch_missing_allocations(cutoff_date, limit)

    if not allocations:
        print(f"✅ No allocations missing transfer IDs from {cutoff_date.strftime('%B %Y')} onwards")
        return {"status": "success", "processed_count": 0, "error_count": 0, "dry_run": dry_run}

    # Group allocations by month
    allocations_by_month = group_allocations_by_month(allocations)

    print(f"Found {len(allocations)} allocations missing transfer IDs across {len(allocations_by_month)} months")
    print(f"Months affected: {', '.join(sorted(allocations_by_month.keys()))}\n")

    # Process each month
    total_processed = 0
    all_errors = []

    for month_key in sorted(allocations_by_month.keys()):
        month_allocations = allocations_by_month[month_key]
        processed_count, errors = process_month_allocations(month_key, month_allocations, children, dry_run)
        total_processed += processed_count
        all_errors.extend(errors)

    # Commit changes
    try:
        commit_changes(total_processed, dry_run)
    except Exception as e:
        print(f"❌ Failed to commit changes: {e}")
        if not dry_run:
            db.session.rollback()
        raise

    # Prepare result
    result = {
        "status": "success" if len(all_errors) == 0 else "completed_with_errors",
        "processed_count": total_processed,
        "error_count": len(all_errors),
        "total_allocations": len(allocations),
        "months_affected": len(allocations_by_month),
        "errors": all_errors,
        "dry_run": dry_run,
        "limit": limit,
    }

    print_summary(result)
    return result


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
