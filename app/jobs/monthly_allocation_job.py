import zoneinfo
from datetime import datetime
from typing import Any

from flask import current_app

from ..constants import BUSINESS_TIMEZONE
from ..services.allocation_service import AllocationService
from ..utils.date_utils import get_next_month_start
from . import job_manager


@job_manager.job
def create_monthly_allocations(from_info: str = "scheduler", **kwargs) -> dict[str, Any]:
    """
    Job that creates monthly allocations for all children on the first day of each month.
    This ensures all children have allocations ready for the new month.
    """
    try:
        # Get first day of next month
        next_month = get_next_month_start()

        current_app.logger.info(
            f"{datetime.now()} Starting monthly allocation creation from {from_info} for {next_month.strftime('%B %Y')}"
        )

        # Use AllocationService to create allocations
        allocation_service = AllocationService(current_app)
        result = allocation_service.create_allocations_for_all_children(target_month=next_month)

        # Build response in the expected format
        response = {
            "status": "success" if result.error_count == 0 else "completed_with_errors",
            "month": next_month.strftime("%B %Y"),
            "created_count": result.created_count,
            "skipped_count": result.skipped_count,
            "error_count": result.error_count,
            "total_children": result.created_count + result.skipped_count + result.error_count,
            "errors": result.errors[:10],  # Limit error list to first 10 for logging
        }

        current_app.logger.info(
            f"{datetime.now()} Monthly allocation creation completed: "
            f"Created {result.created_count}, Skipped {result.skipped_count}, Errors {result.error_count} "
            f"for {next_month.strftime('%B %Y')}"
        )

        return response

    except Exception as e:
        current_app.logger.error(f"Failed to create monthly allocations from {from_info}: {str(e)}")
        raise


def schedule_monthly_allocation_job():
    """
    Schedule the monthly allocation job to run on the 1st of every month at 1:00 AM MST.
    Cron format: minute hour day month day_of_week

    Note: The cron schedule runs in UTC. To run at 1:00 AM MST (UTC-7) / 1:00 AM MDT (UTC-6),
    we schedule for 8:00 AM UTC during standard time or 7:00 AM UTC during daylight time.
    Using 8:00 AM UTC as the base time.
    """
    # Run at 8:00 AM UTC on the 1st of every month (1:00 AM MST / 2:00 AM MDT)
    cron_schedule = current_app.config.get("MONTHLY_ALLOCATION_CRON", "0 8 1 * *")
    from_info = "monthly_scheduler"

    current_app.logger.info(
        f"Scheduling monthly allocation job with cron '{cron_schedule}' in UTC (1:00 AM Mountain Time)"
    )

    return create_monthly_allocations.schedule_cron(cron_schedule, from_info=from_info)


def create_allocations_for_next_month():
    """
    Manually trigger allocation creation for the next month.
    Useful for testing or manual execution.
    """
    current_app.logger.info("Manually triggering monthly allocation creation for next month")

    return create_monthly_allocations.delay(from_info="manual_trigger")
