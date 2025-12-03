from datetime import datetime, timedelta
from typing import Any

from flask import current_app
from sqlalchemy import and_

from ..extensions import db
from ..models import FamilyPaymentSettings, MonthAllocation
from . import job_manager


@job_manager.job
def reclaim_old_allocation_funds(
    days_old: int = 90, minimum_amount_cents: int = 100, dry_run: bool = False, from_info: str = "scheduler", **kwargs
) -> dict[str, Any]:
    """
    Job that reclaims unused funds from old monthly allocations.

    This job finds allocations that are:
    1. Older than the specified number of days
    2. Have remaining unpaid funds (net_allocation_cents > paid_cents, accounting for prior reclamations)
    3. Have a remaining amount above the minimum threshold

    Args:
        days_old: Number of days old an allocation must be to be eligible for reclamation (default: 90)
        minimum_amount_cents: Minimum amount in cents to reclaim (default: 100 = $1.00)
        dry_run: If True, only report what would be reclaimed without actually reclaiming
        from_info: Source of the job execution (e.g., "scheduler", "manual")

    Returns:
        dict with status and reclamation details
    """
    try:
        cutoff_date = datetime.now().date() - timedelta(days=days_old)

        current_app.logger.info(
            f"{datetime.now()} Starting fund reclamation job from {from_info} "
            f"(cutoff_date: {cutoff_date}, min_amount: ${minimum_amount_cents / 100:.2f}, dry_run: {dry_run})"
        )

        # Find old allocations with remaining funds
        # We query all allocations older than cutoff_date and filter in Python
        # to use the remaining_unpaid_cents property
        old_allocations = (
            MonthAllocation.query.filter(MonthAllocation.date < cutoff_date)
            .filter(MonthAllocation.chek_transfer_id.isnot(None))  # Only allocations that had funds transferred
            .all()
        )

        eligible_allocations = []
        for allocation in old_allocations:
            remaining = allocation.remaining_unpaid_cents
            if remaining >= minimum_amount_cents:
                eligible_allocations.append((allocation, remaining))

        current_app.logger.info(
            f"Found {len(eligible_allocations)} allocations eligible for reclamation "
            f"(out of {len(old_allocations)} old allocations checked)"
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
                    # Get family payment settings to find chek_user_id
                    family_payment_settings = FamilyPaymentSettings.query.join(
                        MonthAllocation, MonthAllocation.child_supabase_id == allocation.child_supabase_id
                    ).first()

                    if not family_payment_settings or not family_payment_settings.chek_user_id:
                        raise ValueError(f"No family payment settings found for child {allocation.child_supabase_id}")

                    # Reclaim the funds
                    response = current_app.payment_service.reclaim_funds(
                        chek_user_id=int(family_payment_settings.chek_user_id),
                        amount=remaining_amount,
                        month_allocation_id=allocation.id,
                    )

                    current_app.logger.info(
                        f"Successfully reclaimed ${remaining_amount / 100:.2f} from allocation {allocation.id} "
                        f"(transfer_id: {response.transfer.id if response and response.transfer else 'N/A'})"
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
            "cutoff_date": cutoff_date.isoformat(),
            "minimum_amount_cents": minimum_amount_cents,
            "checked_count": len(old_allocations),
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
    days_old = current_app.config.get("RECLAIM_FUNDS_DAYS_OLD", 90)
    minimum_amount_cents = current_app.config.get("RECLAIM_FUNDS_MIN_AMOUNT_CENTS", 100)
    from_info = "monthly_scheduler"

    current_app.logger.info(
        f"Scheduling fund reclamation job with cron '{cron_schedule}' in UTC (2 AM MST / 3 AM MDT), "
        f"days_old={days_old}, min_amount=${minimum_amount_cents / 100:.2f}"
    )

    return reclaim_old_allocation_funds.schedule_cron(
        cron_schedule, days_old=days_old, minimum_amount_cents=minimum_amount_cents, from_info=from_info
    )


def reclaim_old_allocations_now(days_old: int = 90, minimum_amount_cents: int = 100, dry_run: bool = True):
    """
    Manually trigger fund reclamation for old allocations.
    Useful for testing or manual execution.

    Args:
        days_old: Number of days old an allocation must be (default: 90)
        minimum_amount_cents: Minimum amount to reclaim in cents (default: 100 = $1.00)
        dry_run: If True, only reports what would be reclaimed (default: True)
    """
    current_app.logger.info(
        f"Manually triggering fund reclamation for allocations older than {days_old} days "
        f"with minimum ${minimum_amount_cents / 100:.2f} (dry_run: {dry_run})"
    )

    return reclaim_old_allocation_funds.delay(
        days_old=days_old, minimum_amount_cents=minimum_amount_cents, dry_run=dry_run, from_info="manual_trigger"
    )
