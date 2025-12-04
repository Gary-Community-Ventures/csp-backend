import os

import sentry_sdk
from flask import current_app
from rq_scheduler import Scheduler

from app import create_app
from app.jobs.attendance import (
    schedule_attendance_communications_job,
    schedule_attendance_job,
)
from app.jobs.invite_reminder import schedule_invite_reminders_job
from app.jobs.monthly_allocation_job import schedule_monthly_allocation_job
from app.jobs.payment_reminders import schedule_payment_reminders_job
from app.jobs.reclaim_unused_allocation_funds import (
    schedule_reclaim_unused_allocation_funds_job,
)
from app.utils.redis import create_redis_connection

JOBS = [
    schedule_monthly_allocation_job,
    schedule_attendance_job,
    schedule_attendance_communications_job,
    schedule_reclaim_unused_allocation_funds_job,
    schedule_invite_reminders_job,
    schedule_payment_reminders_job,
]

if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        try:
            redis_url = os.getenv("REDIS_URL")
            if not redis_url:
                raise ValueError("REDIS_URL environment variable must be set")

            current_app.logger.info("Starting custom RQ scheduler with SSL support...")

            # Create Redis connection with SSL support using shared utility
            redis_conn = create_redis_connection(redis_url)
            scheduler = Scheduler(connection=redis_conn)

            # Clear all existing scheduled jobs to prevent orphaned jobs
            current_app.logger.info("Clearing all existing scheduled jobs...")
            for job in scheduler.get_jobs():
                try:
                    current_app.logger.info(f"Removing scheduled job: {job.id}")
                    scheduler.cancel(job)
                except Exception as e:
                    current_app.logger.error(f"Failed to cancel job {job.id}: {e}")
                    sentry_sdk.capture_exception(e)

            # Schedule system level jobs here
            for job in JOBS:
                job()

            current_app.logger.info("RQ Scheduler started successfully")

            # Run the scheduler
            scheduler.run()

        except KeyboardInterrupt:
            current_app.logger.info("Scheduler stopped by user")
        except Exception as e:
            current_app.logger.error(f"Scheduler error: {e}")
            sentry_sdk.capture_exception(e)
            raise
