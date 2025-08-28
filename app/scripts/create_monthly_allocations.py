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
from datetime import date, datetime, timedelta
from typing import Any, Dict

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app import create_app
from app.config import DAYS_TO_NEXT_MONTH
from app.extensions import db
from app.models.month_allocation import MonthAllocation
from app.sheets.mappings import ChildColumnNames, get_children

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

        # Get all children from Google Sheets
        try:
            all_children = get_children()
        except Exception as e:
            print(f"❌ Failed to fetch children from Google Sheets: {e}")
            raise

        if not all_children:
            print("⚠️  No children found in Google Sheets")
            return {"status": "success", "created_count": 0, "skipped_count": 0, "error_count": 0}

        created_count = 0
        skipped_count = 0
        error_count = 0
        errors = []

        print(f"Found {len(all_children)} children to process\n")

        # Process each child
        for child_data in all_children:
            child_id = child_data.get(ChildColumnNames.ID)
            child_name = (
                f"{child_data.get(ChildColumnNames.FIRST_NAME)} {child_data.get(ChildColumnNames.LAST_NAME)}"
            )

            if not child_id:
                print(f"⚠️  Skipping child with missing ID: {child_name}")
                error_count += 1
                errors.append(f"Missing ID for child: {child_name}")
                continue

            try:
                # Check if allocation already exists for target month
                existing_allocation = MonthAllocation.query.filter_by(
                    google_sheets_child_id=child_id, date=target_month
                ).first()

                if existing_allocation:
                    print(f"⏭️  {child_name} ({child_id}) - Already exists (${existing_allocation.allocation_cents / 100:.2f})")
                    skipped_count += 1
                    continue

                if dry_run:
                    # In dry run, just show what would be created
                    try:
                        # Get allocation amount that would be created
                        from app.models.month_allocation import get_allocation_amount
                        allocation_cents = get_allocation_amount(child_id)
                        print(f"✨ {child_name} ({child_id}) - Would create ${allocation_cents / 100:.2f}")
                        created_count += 1
                    except Exception as e:
                        print(f"❌ {child_name} ({child_id}) - Would fail: {e}")
                        error_count += 1
                        errors.append(f"{child_name} ({child_id}): {str(e)}")
                else:
                    # Create new allocation using the existing method
                    allocation = MonthAllocation.get_or_create_for_month(child_id, target_month)
                    print(f"✅ {child_name} ({child_id}) - Created ${allocation.allocation_cents / 100:.2f}")
                    created_count += 1

            except ValueError as e:
                # Handle specific validation errors from get_or_create_for_month
                print(f"❌ {child_name} ({child_id}) - Validation error: {e}")
                error_count += 1
                errors.append(f"{child_name} ({child_id}): {str(e)}")
                continue

            except Exception as e:
                # Handle unexpected errors
                print(f"❌ {child_name} ({child_id}) - Unexpected error: {e}")
                error_count += 1
                errors.append(f"{child_name} ({child_id}): {str(e)}")
                continue

        # Final commit for all successful allocations (unless dry run)
        if not dry_run:
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"❌ Failed to commit monthly allocations: {e}")
                raise

        result = {
            "status": "success",
            "month": target_month.strftime("%B %Y"),
            "created_count": created_count,
            "skipped_count": skipped_count,
            "error_count": error_count,
            "total_children": len(all_children),
            "errors": errors,
            "dry_run": dry_run,
        }

        # Print summary
        print(f"\n{'=' * 60}")
        print(f"{'DRY RUN ' if dry_run else ''}SUMMARY for {target_month.strftime('%B %Y')}:")
        print(f"  ✅ {'Would create' if dry_run else 'Created'}: {created_count}")
        print(f"  ⏭️  Skipped (already exists): {skipped_count}")
        print(f"  ❌ Errors: {error_count}")
        print(f"  📊 Total children: {len(all_children)}")

        if errors and error_count > 0:
            print(f"\nFirst few errors:")
            for error in errors[:5]:
                print(f"  • {error}")
            if len(errors) > 5:
                print(f"  ... and {len(errors) - 5} more errors")

        return result

    except Exception as e:
        print(f"❌ Failed to create monthly allocations: {str(e)}")
        if not dry_run:
            db.session.rollback()
        raise


def create_allocations_for_current_month(dry_run: bool = False) -> Dict[str, Any]:
    """Create allocations for the current month."""
    current_month = date.today().replace(day=1)
    return create_allocations_for_month(current_month, dry_run)


def create_allocations_for_next_month(dry_run: bool = False) -> Dict[str, Any]:
    """Create allocations for the next month."""
    today = date.today()
    current_month = today.replace(day=1)
    next_month = (current_month + timedelta(days=DAYS_TO_NEXT_MONTH)).replace(day=1)
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