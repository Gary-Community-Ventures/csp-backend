import os
import subprocess
from app import create_app
from app.jobs.example_job import example_schedule_job
from flask import current_app
import sentry_sdk

if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        # Schedule system level jobs here
        example_schedule_job()

        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            raise ValueError("REDIS_URL environment variable must be set")

        try:
            current_app.logger.info("Starting rqscheduler...")
            subprocess.run(
                ["rqscheduler", "--url", redis_url], check=True, timeout=60 * 5  # 5 minutes timeout, adjust as needed
            )
            current_app.logger.info("rqscheduler started successfully.")
        except subprocess.TimeoutExpired as e:
            current_app.logger.error(f"Timeout expired when starting rqscheduler: {e}")
            sentry_sdk.capture_exception(e)
            raise
        except subprocess.CalledProcessError as e:
            current_app.logger.error(f"rqscheduler failed with exit code {e.returncode}: {e}")
            sentry_sdk.capture_exception(e)
            raise
        except Exception as e:
            current_app.logger.error(f"Unexpected error when starting rqscheduler: {e}")
            sentry_sdk.capture_exception(e)
            raise
