from datetime import datetime
from typing import Any

from flask import current_app

from app.utils.date_utils import get_current_month_start

from ..models import MonthAllocation
from . import job_manager


@job_manager.job
def reclaim_past_month_funds(
    minimum_amount_cents: int = 100, dry_run: bool = False, from_info: str = "scheduler", **kwargs
) -> dict[str, Any]:
    """
    Job that reclaims unused funds from monthly allocations in past months.

    This job finds allocations that are:
    1. From months before the current month
    2. Have remaining unpaid funds (net_allocation_cents > paid_cents, accounting for prior reclamations)
    3. Have a remaining amount above the minimum threshold

    Args:
        minimum_amount_cents: Minimum amount in cents to reclaim (default: 100 = $1.00)
        dry_run: If True, only report what would be reclaimed without actually reclaiming
        from_info: Source of the job execution (e.g., "scheduler", "manual")

    Returns:
        dict with status and reclamation details
    """
    try:
        current_month_start = get_current_month_start()

        current_app.logger.info(
            f"{datetime.now()} Starting fund reclamation job from {from_info} "
            f"(current_month: {current_month_start}, min_amount: ${minimum_amount_cents / 100:.2f}, dry_run: {dry_run})"
        )

        # Find allocations from past months with funds transferred
        past_allocations = (
            MonthAllocation.query.filter(MonthAllocation.date < current_month_start)
            .filter(MonthAllocation.chek_transfer_id.isnot(None))  # Only allocations that had funds transferred
            .all()
        )

        eligible_allocations = []
        for allocation in past_allocations:
            remaining = allocation.remaining_unpaid_cents
            if remaining >= minimum_amount_cents:
                eligible_allocations.append((allocation, remaining))

        current_app.logger.info(
            f"Found {len(eligible_allocations)} allocations eligible for reclamation "
            f"(out of {len(past_allocations)} past allocations checked)"
        )

        if len(eligible_allocations) == 0:
            return {
                "status": "success",
                "message": "No allocations found for reclamation",
                "reclaimed_count": 0,
                "total_amount_cents": 0,
                "error_count": 0,
                "errors": [],
            }

        reclaimed_count = 0
        error_count = 0
        total_amount_cents = 0
        errors = []

        for allocation, remaining_amount in eligible_allocations:
            try:
                current_app.logger.info(
                    f"{'[DRY RUN] Would reclaim' if dry_run else 'Reclaiming'} ${remaining_amount / 100:.2f} "
                    f"from allocation {allocation.id} (child: {allocation.child_supabase_id}, "
                    f"date: {allocation.date.strftime('%Y-%m')})"
                )

                if not dry_run:
                    # Use the MonthAllocation's reclaim method
                    fund_reclamation = allocation.reclaim_remaining_funds()

                    current_app.logger.info(
                        f"Successfully reclaimed ${remaining_amount / 100:.2f} from allocation {allocation.id} "
                        f"(reclamation_id: {fund_reclamation.id if fund_reclamation else 'N/A'})"
                    )

                reclaimed_count += 1
                total_amount_cents += remaining_amount

            except Exception as e:
                error_count += 1
                error_msg = (
                    f"Failed to reclaim funds from allocation {allocation.id} "
                    f"(child: {allocation.child_supabase_id}): {str(e)}"
                )
                current_app.logger.error(error_msg, exc_info=True)
                errors.append(error_msg)

        response = {
            "status": "success" if error_count == 0 else "completed_with_errors",
            "dry_run": dry_run,
            "current_month": current_month_start.isoformat(),
            "minimum_amount_cents": minimum_amount_cents,
            "checked_count": len(past_allocations),
            "eligible_count": len(eligible_allocations),
            "reclaimed_count": reclaimed_count,
            "total_amount_cents": total_amount_cents,
            "total_amount_dollars": total_amount_cents / 100,
            "error_count": error_count,
            "errors": errors[:10],  # Limit error list to first 10 for logging
        }

        current_app.logger.info(
            f"{datetime.now()} Fund reclamation job completed: "
            f"{'[DRY RUN] Would reclaim' if dry_run else 'Reclaimed'} ${total_amount_cents / 100:.2f} "
            f"from {reclaimed_count} allocations, {error_count} errors"
        )

        return response

    except Exception as e:
        current_app.logger.error(f"Failed to run fund reclamation job from {from_info}: {str(e)}", exc_info=True)
        raise


@job_manager.job
def reclaim_funds_for_month(
    target_month: str, minimum_amount_cents: int = 100, dry_run: bool = False, from_info: str = "manual", **kwargs
) -> dict[str, Any]:
    """
    Job that reclaims unused funds from allocations for a specific month.

    Args:
        target_month: Month to reclaim from in YYYY-MM format (e.g., "2024-03")
        minimum_amount_cents: Minimum amount in cents to reclaim (default: 100 = $1.00)
        dry_run: If True, only report what would be reclaimed without actually reclaiming
        from_info: Source of the job execution (e.g., "manual", "api")

    Returns:
        dict with status and reclamation details
    """
    try:
        # Parse target month
        month_date = datetime.strptime(target_month, "%Y-%m").date().replace(day=1)

        current_app.logger.info(
            f"{datetime.now()} Starting fund reclamation for month {target_month} from {from_info} "
            f"(min_amount: ${minimum_amount_cents / 100:.2f}, dry_run: {dry_run})"
        )

        # Find allocations for the specific month
        month_allocations = (
            MonthAllocation.query.filter(MonthAllocation.date == month_date)
            .filter(MonthAllocation.chek_transfer_id.isnot(None))  # Only allocations that had funds transferred
            .all()
        )

        eligible_allocations = []
        for allocation in month_allocations:
            remaining = allocation.remaining_unpaid_cents
            if remaining >= minimum_amount_cents:
                eligible_allocations.append((allocation, remaining))

        current_app.logger.info(
            f"Found {len(eligible_allocations)} allocations eligible for reclamation "
            f"(out of {len(month_allocations)} allocations for {target_month})"
        )

        if len(eligible_allocations) == 0:
            return {
                "status": "success",
                "message": f"No allocations found for reclamation in {target_month}",
                "target_month": target_month,
                "reclaimed_count": 0,
                "total_amount_cents": 0,
                "error_count": 0,
                "errors": [],
            }

        reclaimed_count = 0
        error_count = 0
        total_amount_cents = 0
        errors = []

        for allocation, remaining_amount in eligible_allocations:
            try:
                current_app.logger.info(
                    f"{'[DRY RUN] Would reclaim' if dry_run else 'Reclaiming'} ${remaining_amount / 100:.2f} "
                    f"from allocation {allocation.id} (child: {allocation.child_supabase_id})"
                )

                if not dry_run:
                    # Use the MonthAllocation's reclaim method
                    fund_reclamation = allocation.reclaim_remaining_funds()

                    current_app.logger.info(
                        f"Successfully reclaimed ${remaining_amount / 100:.2f} from allocation {allocation.id} "
                        f"(reclamation_id: {fund_reclamation.id if fund_reclamation else 'N/A'})"
                    )

                reclaimed_count += 1
                total_amount_cents += remaining_amount

            except Exception as e:
                error_count += 1
                error_msg = (
                    f"Failed to reclaim funds from allocation {allocation.id} "
                    f"(child: {allocation.child_supabase_id}): {str(e)}"
                )
                current_app.logger.error(error_msg, exc_info=True)
                errors.append(error_msg)

        response = {
            "status": "success" if error_count == 0 else "completed_with_errors",
            "dry_run": dry_run,
            "target_month": target_month,
            "minimum_amount_cents": minimum_amount_cents,
            "checked_count": len(month_allocations),
            "eligible_count": len(eligible_allocations),
            "reclaimed_count": reclaimed_count,
            "total_amount_cents": total_amount_cents,
            "total_amount_dollars": total_amount_cents / 100,
            "error_count": error_count,
            "errors": errors[:10],  # Limit error list to first 10 for logging
        }

        current_app.logger.info(
            f"{datetime.now()} Fund reclamation job for {target_month} completed: "
            f"{'[DRY RUN] Would reclaim' if dry_run else 'Reclaimed'} ${total_amount_cents / 100:.2f} "
            f"from {reclaimed_count} allocations, {error_count} errors"
        )

        return response

    except ValueError as e:
        error_msg = f"Invalid target_month format '{target_month}': {str(e)}"
        current_app.logger.error(error_msg)
        raise ValueError(error_msg)
    except Exception as e:
        current_app.logger.error(
            f"Failed to run fund reclamation job for {target_month} from {from_info}: {str(e)}", exc_info=True
        )
        raise


def schedule_reclaim_old_allocation_funds_job():
    """
    Schedule the fund reclamation job to run monthly.
    Runs on the 5th of every month at 2:00 AM MST / 3:00 AM MDT.

    Note: The cron schedule runs in UTC at 9:00 AM. Due to daylight saving time,
    this translates to 2:00 AM during Mountain Standard Time (winter) and 3:00 AM during
    Mountain Daylight Time (summer).
    """
    # Run at 9:00 AM UTC on the 5th of every month (2:00 AM MST / 3:00 AM MDT)
    cron_schedule = current_app.config.get("RECLAIM_FUNDS_CRON", "0 9 5 * *")
    minimum_amount_cents = current_app.config.get("RECLAIM_FUNDS_MIN_AMOUNT_CENTS", 100)
    from_info = "monthly_scheduler"

    current_app.logger.info(
        f"Scheduling fund reclamation job with cron '{cron_schedule}' in UTC (2 AM MST / 3 AM MDT), "
        f"min_amount=${minimum_amount_cents / 100:.2f}"
    )

    return reclaim_past_month_funds.schedule_cron(
        cron_schedule, minimum_amount_cents=minimum_amount_cents, from_info=from_info
    )


def reclaim_past_months_now(minimum_amount_cents: int = 100, dry_run: bool = True):
    """
    Manually trigger fund reclamation for all past month allocations.
    Useful for testing or manual execution.

    Args:
        minimum_amount_cents: Minimum amount to reclaim in cents (default: 100 = $1.00)
        dry_run: If True, only reports what would be reclaimed (default: True)
    """
    current_app.logger.info(
        f"Manually triggering fund reclamation for all past month allocations "
        f"with minimum ${minimum_amount_cents / 100:.2f} (dry_run: {dry_run})"
    )

    return reclaim_past_month_funds.delay(
        minimum_amount_cents=minimum_amount_cents, dry_run=dry_run, from_info="manual_trigger"
    )


def reclaim_specific_month_now(target_month: str, minimum_amount_cents: int = 100, dry_run: bool = True):
    """
    Manually trigger fund reclamation for a specific month.
    Useful for testing or manual execution.

    Args:
        target_month: Month to reclaim from in YYYY-MM format (e.g., "2024-03")
        minimum_amount_cents: Minimum amount to reclaim in cents (default: 100 = $1.00)
        dry_run: If True, only reports what would be reclaimed (default: True)
    """
    current_app.logger.info(
        f"Manually triggering fund reclamation for {target_month} "
        f"with minimum ${minimum_amount_cents / 100:.2f} (dry_run: {dry_run})"
    )

    return reclaim_funds_for_month.delay(
        target_month=target_month,
        minimum_amount_cents=minimum_amount_cents,
        dry_run=dry_run,
        from_info="manual_trigger",
    )
