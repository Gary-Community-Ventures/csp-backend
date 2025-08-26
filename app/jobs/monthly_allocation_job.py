from datetime import date, datetime, timedelta
from typing import Any, Dict

from flask import current_app

from ..extensions import db
from ..models.month_allocation import MonthAllocation
from ..sheets.mappings import ChildColumnNames, get_children
from . import job_manager


@job_manager.job
def create_monthly_allocations(from_info: str = "scheduler", **kwargs) -> Dict[str, Any]:
    """
    Job that creates monthly allocations for all children on the first day of each month.
    This ensures all children have allocations ready for the new month.
    """
    try:
        # Calculate next month (the month we want to create allocations for)
        today = date.today()
        current_month = today.replace(day=1)
        # Get first day of next month
        next_month = (current_month + timedelta(days=32)).replace(day=1)

        current_app.logger.info(
            f"{datetime.now()} Starting monthly allocation creation from {from_info} for {next_month.strftime('%B %Y')}"
        )

        # Get all children from Google Sheets
        try:
            all_children = get_children()
        except Exception as e:
            current_app.logger.error(f"Failed to fetch children from Google Sheets: {e}")
            raise

        if not all_children:
            current_app.logger.warning("No children found in Google Sheets")
            return {"status": "success", "created_count": 0, "skipped_count": 0, "error_count": 0}

        created_count = 0
        skipped_count = 0
        error_count = 0
        errors = []

        # Process each child
        for child_data in all_children:
            child_id = child_data.get(ChildColumnNames.ID)
            child_name = (
                f"{child_data.get(ChildColumnNames.FIRST_NAME, '')} {child_data.get(ChildColumnNames.LAST_NAME, '')}"
            )

            if not child_id:
                current_app.logger.warning(f"Skipping child with missing ID: {child_name}")
                error_count += 1
                errors.append(f"Missing ID for child: {child_name}")
                continue

            try:
                # Check if allocation already exists for next month
                existing_allocation = MonthAllocation.query.filter_by(
                    google_sheets_child_id=child_id, date=next_month
                ).first()

                if existing_allocation:
                    current_app.logger.debug(
                        f"Allocation already exists for {child_name} ({child_id}) for {next_month}"
                    )
                    skipped_count += 1
                    continue

                # Create new allocation using the existing method
                allocation = MonthAllocation.get_or_create_for_month(child_id, next_month)

                current_app.logger.info(
                    f"Created allocation for {child_name} ({child_id}): ${allocation.allocation_cents / 100:.2f}"
                )
                created_count += 1

            except ValueError as e:
                # Handle specific validation errors from get_for_month
                current_app.logger.error(f"Validation error creating allocation for {child_name} ({child_id}): {e}")
                error_count += 1
                errors.append(f"{child_name} ({child_id}): {str(e)}")
                continue

            except Exception as e:
                # Handle unexpected errors
                current_app.logger.error(f"Unexpected error creating allocation for {child_name} ({child_id}): {e}")
                error_count += 1
                errors.append(f"{child_name} ({child_id}): {str(e)}")
                continue

        # Final commit for all successful allocations
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Failed to commit monthly allocations: {e}")
            raise

        result = {
            "status": "success",
            "month": next_month.strftime("%B %Y"),
            "created_count": created_count,
            "skipped_count": skipped_count,
            "error_count": error_count,
            "total_children": len(all_children),
            "errors": errors[:10],  # Limit error list to first 10 for logging
        }

        current_app.logger.info(
            f"{datetime.now()} Monthly allocation creation completed: "
            f"Created {created_count}, Skipped {skipped_count}, Errors {error_count} "
            f"for {next_month.strftime('%B %Y')}"
        )

        return result

    except Exception as e:
        current_app.logger.error(f"Failed to create monthly allocations from {from_info}: {str(e)}")
        db.session.rollback()
        raise


def schedule_monthly_allocation_job():
    """
    Schedule the monthly allocation job to run on the 1st of every month at 1:00 AM.
    Cron format: minute hour day month day_of_week
    """
    # Run at 1:00 AM on the 1st of every month
    cron_schedule = current_app.config.get("MONTHLY_ALLOCATION_CRON", "0 1 1 * *")
    from_info = "monthly_scheduler"

    current_app.logger.info(f"Scheduling monthly allocation job with cron '{cron_schedule}'")

    return create_monthly_allocations.schedule_cron(cron_schedule, from_info=from_info)


def create_allocations_for_next_month():
    """
    Manually trigger allocation creation for the next month.
    Useful for testing or manual execution.
    """
    current_app.logger.info("Manually triggering monthly allocation creation for next month")

    return create_monthly_allocations.delay(from_info="manual_trigger")
