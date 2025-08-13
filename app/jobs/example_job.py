from datetime import datetime, timedelta
import time
from . import job
from flask import current_app


@job
def example_job(user_id, from_info, **kwargs):
    """Example task of something that runs in the background"""
    try:
        current_app.logger.info(
            f"{datetime.now()} Processing task from {from_info} for user {user_id} with args: {kwargs}"
        )

        # Simulate some processing
        sleep_time = kwargs.get("sleep_time", 0)
        if sleep_time > 0:
            current_app.logger.info(f"{datetime.now()} Sleeping for {sleep_time} seconds...")
            time.sleep(sleep_time)
        current_app.logger.info(f"{datetime.now()} Task from {from_info} finished for user {user_id} after sleeping.")

    except Exception as e:
        current_app.logger.error(f"Failed to process task from {from_info} for user {user_id}: {str(e)}")
        raise

    return {"status": "success", "user_id": user_id, **kwargs}


def example_call_job_from_function(user_id, delay_seconds=0, sleep_time=0, **kwargs):
    """Queue a job to run in the background"""
    if delay_seconds > 0:
        return example_job.delay_in(
            timedelta(seconds=delay_seconds),
            user_id=user_id,
            from_info=kwargs.get('from_info', 'unknown'),
            sleep_time=sleep_time,
            **{k: v for k, v in kwargs.items() if k != 'from_info'}
        )
    else:
        return example_job.delay(
            user_id=user_id,
            from_info=kwargs.get('from_info', 'unknown'),
            sleep_time=sleep_time,
            **{k: v for k, v in kwargs.items() if k != 'from_info'}
        )


def example_schedule_job():
    """Schedule job"""
    # Schedule job to run every 5 minutes
    # TODO remove this once we have tested the scheduler in production
    from_info = "daily_scheduler"
    current_app.logger.info(f"Scheduling daily job from {from_info}...")
    return example_job.schedule_cron(
        '*/1 * * * *',  # Every 5 minutes
        user_id=None,
        from_info=from_info,
        sleep_time=10
    )

