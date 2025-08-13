import os
import subprocess
from app import create_app
from app.jobs.example_job import example_schedule_job

if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        # Schedule system level jobs here
        # For example, scheduling a daily job
        example_schedule_job()

    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        raise ValueError("REDIS_URL environment variable must be set")

    # Start the RQ scheduler
    subprocess.run(["rqscheduler", "--url", redis_url])
