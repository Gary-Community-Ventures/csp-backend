import os
import time

import sentry_sdk
from flask import current_app
from rq_scheduler import Scheduler

from app import create_app
from app.jobs.example_job import example_schedule_job
from app.utils.redis import create_redis_connection


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        try:
            # Schedule system level jobs here
            example_schedule_job()

            redis_url = os.getenv("REDIS_URL")
            if not redis_url:
                raise ValueError("REDIS_URL environment variable must be set")

            current_app.logger.info("Starting custom RQ scheduler with SSL support...")

            # Create Redis connection with SSL support using shared utility
            redis_conn = create_redis_connection(redis_url)
            scheduler = Scheduler(connection=redis_conn)

            current_app.logger.info("RQ Scheduler started successfully")

            # Run the scheduler
            scheduler.run()

        except KeyboardInterrupt:
            current_app.logger.info("Scheduler stopped by user")
        except Exception as e:
            current_app.logger.error(f"Scheduler error: {e}")
            sentry_sdk.capture_exception(e)
            raise
