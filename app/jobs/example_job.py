from datetime import datetime, timedelta
from . import get_queue, get_scheduler
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
    queue = get_queue()

    if delay_seconds > 0:
        return queue.enqueue_in(
            timedelta(seconds=delay_seconds), example_job, user_id=user_id, sleep_time=sleep_time, **kwargs
        )
    else:
        return queue.enqueue(example_job, user_id=user_id, sleep_time=sleep_time, **kwargs)


def example_schedule_job():
    """Schedule job"""
    scheduler = get_scheduler()

    # Run every day at 2 AM
    return scheduler.cron(
        cron_string="0 2 * * *",
        func=example_job,
        kwargs={"user_id": None, "from_info": "daily_scheduler", "sleep_time": 10},
        id="daily_job",
    )
