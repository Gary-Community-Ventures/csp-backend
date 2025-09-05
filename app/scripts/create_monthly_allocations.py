#!/usr/bin/env python
"""
Manual monthly allocation creation script.

Usage:
    python app/scripts/create_monthly_allocations.py                    # Create for current month
    python app/scripts/create_monthly_allocations.py --month 2024-03   # Create for specific month
    python app/scripts/create_monthly_allocations.py --next-month      # Create for next month
    python app/scripts/create_monthly_allocations.py --dry-run         # Show what would be created
"""

import argparse
import os
import sys
from datetime import date, datetime
from typing import Any, Dict

from app.supabase.helpers import format_name
from app.supabase.tables import Child

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app import create_app
from app.services.allocation_service import AllocationService
from app.utils.date_utils import get_current_month_start, get_next_month_start

# Create Flask app context
app = create_app()
app.app_context().push()


def create_allocations_for_month(target_month: date, dry_run: bool = False) -> Dict[str, Any]:
    """
    Create monthly allocations for all children for a specific month.

    Args:
        target_month: Date representing the first day of the target month
        dry_run: If True, show what would be created without actually creating

    Returns:
        Dict with results: created_count, skipped_count, error_count, etc.
    """
    try:
        # Ensure target_month is first day of month
        target_month = target_month.replace(day=1)

        print(f"\n{'[DRY RUN] ' if dry_run else ''}Creating monthly allocations for {target_month.strftime('%B %Y')}")
        print("-" * 60)

        # Progress callback to print updates for each child
        def print_progress(child_data, status):
            child_id = Child.ID(child_data)
            child_name = format_name(child_data)

            if status == "created":
                # Try to get the allocation amount if available
                try:
                    from app.models.month_allocation import get_allocation_amount

                    allocation_cents = get_allocation_amount(child_id)
                    amount_str = f" (${allocation_cents / 100:.2f})"
                except:
                    amount_str = ""

                if dry_run:
                    print(f"✨ {child_name} ({child_id}) - Would create{amount_str}")
                else:
                    print(f"✅ {child_name} ({child_id}) - Created{amount_str}")
            elif status == "skipped":
                print(f"⏭️  {child_name} ({child_id}) - Already exists")
            elif status == "error":
                print(f"❌ {child_name} ({child_id}) - Failed")

        # Use AllocationService
        allocation_service = AllocationService(app)
        result = allocation_service.create_allocations_for_all_children(
            target_month=target_month, dry_run=dry_run, progress_callback=print_progress
        )

        # Build final result dict
        result_dict = {
            "status": "success" if result.error_count == 0 else "completed_with_errors",
            "month": target_month.strftime("%B %Y"),
            "created_count": result.created_count,
            "skipped_count": result.skipped_count,
            "error_count": result.error_count,
            "total_children": result.created_count + result.skipped_count + result.error_count,
            "errors": result.errors,
            "dry_run": dry_run,
        }

        # Print summary
        print(f"\n{'=' * 60}")
        print(f"{'DRY RUN ' if dry_run else ''}SUMMARY for {target_month.strftime('%B %Y')}:")
        print(f"  ✅ {'Would create' if dry_run else 'Created'}: {result_dict['created_count']}")
        print(f"  ⏭️  Skipped (already exists): {result_dict['skipped_count']}")
        print(f"  ❌ Errors: {result_dict['error_count']}")
        print(f"  📊 Total children: {result_dict['total_children']}")

        if result_dict["errors"] and result_dict["error_count"] > 0:
            print(f"\nFirst few errors:")
            for error in result_dict["errors"][:5]:
                print(f"  • {error}")
            if len(result_dict["errors"]) > 5:
                print(f"  ... and {len(result_dict['errors']) - 5} more errors")

        return result_dict

    except Exception as e:
        print(f"❌ Failed to create monthly allocations: {str(e)}")
        raise


def create_allocations_for_current_month(dry_run: bool = False) -> Dict[str, Any]:
    """Create allocations for the current month."""
    current_month = get_current_month_start()
    return create_allocations_for_month(current_month, dry_run)


def create_allocations_for_next_month(dry_run: bool = False) -> Dict[str, Any]:
    """Create allocations for the next month."""
    next_month = get_next_month_start()
    return create_allocations_for_month(next_month, dry_run)


def main():
    parser = argparse.ArgumentParser(
        description="Create monthly allocations for children.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python app/scripts/create_monthly_allocations.py
  python app/scripts/create_monthly_allocations.py --month 2024-03
  python app/scripts/create_monthly_allocations.py --next-month
  python app/scripts/create_monthly_allocations.py --dry-run --month 2024-04
        """,
    )
    parser.add_argument("--month", type=str, help="Create for specific month (YYYY-MM format)")
    parser.add_argument("--next-month", action="store_true", help="Create for next month")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be created without actually creating")

    args = parser.parse_args()

    try:
        # Determine target month
        if args.month:
            try:
                target_month = datetime.strptime(args.month, "%Y-%m").date()
            except ValueError:
                print(f"❌ Invalid month format: {args.month}. Use YYYY-MM (e.g., 2024-03)")
                sys.exit(1)

            result = create_allocations_for_month(target_month, args.dry_run)

        elif args.next_month:
            result = create_allocations_for_next_month(args.dry_run)

        else:
            # Default: create for current month
            result = create_allocations_for_current_month(args.dry_run)

        # Exit with success if no errors, otherwise exit with failure
        sys.exit(0 if result["error_count"] == 0 else 1)

    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
