from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional
from redis import Redis
from rq import Queue
from rq.job import Job
from rq_scheduler import Scheduler
import functools
from flask import Flask, has_app_context, current_app
from datetime import timedelta
import sentry_sdk
import dataclasses


def _sanitize_exc_info(exc_info: Optional[str]) -> Optional[str]:
    """Sanitizes exception information to prevent sensitive data leakage."""
    if exc_info:
        # Extract only the first line of the traceback, which usually contains the error message
        first_line = exc_info.split("\n")[0]
        return f"Error: {first_line}"
    return None


@dataclasses.dataclass
class JobStatus:
    id: str
    status: str
    result: Any
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    exc_info: Optional[str] = None


@dataclasses.dataclass
class JobInfo:
    id: str
    func_name: str
    created_at: datetime
    status: str


@dataclasses.dataclass
class QueueInfo:
    name: str
    length: int
    jobs: List[JobInfo]


@dataclasses.dataclass
class JobActionResult:
    status: str
    job_id: Optional[str] = None
    error: Optional[str] = None


class JobManager:
    def __init__(self, app: Flask = None):
        self.redis_conn = None
        self.job_queue = None
        self.job_scheduler = None
        if app:
            self.init_app(app)

    def init_app(self, app: Flask):
        redis_url = app.config.get("REDIS_URL", "redis://localhost:6379/0")
        self.redis_conn = Redis.from_url(redis_url)
        self.job_queue = Queue(connection=self.redis_conn)
        self.job_scheduler = Scheduler(connection=self.redis_conn)

        if not hasattr(app, "extensions"):
            app.extensions = {}
        app.extensions["job_manager"] = self

    def get_queue(self):
        return self.job_queue

    def get_scheduler(self):
        return self.job_scheduler

    def get_redis(self):
        return self.redis_conn

    def job(self, func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if has_app_context():
                return func(*args, **kwargs)
            else:
                from app import create_app

                app = create_app()
                with app.app_context():
                    return func(*args, **kwargs)

        wrapper.__name__ = func.__name__
        wrapper.__module__ = func.__module__
        wrapper.__qualname__ = func.__qualname__

        def delay(*args, **kwargs):
            return self.get_queue().enqueue(wrapper, *args, **kwargs)

        def delay_in(delay: timedelta, *args, **kwargs):
            return self.get_queue().enqueue_in(delay, wrapper, *args, **kwargs)

        def schedule_cron(cron_string: str, *args, **kwargs):
            return self.get_scheduler().cron(cron_string, wrapper, args=args, kwargs=kwargs)

        wrapper.delay = delay
        wrapper.delay_in = delay_in
        wrapper.schedule_cron = schedule_cron

        return wrapper

    def get_job_status(self, job_id: str) -> Optional[JobStatus]:
        try:
            job = Job.fetch(job_id, connection=self.get_redis())
            sanitized_exc_info = _sanitize_exc_info(job.exc_info)
            return JobStatus(
                id=job.id,
                status=job.status,
                result=job.result,
                created_at=job.created_at,
                started_at=job.started_at,
                ended_at=job.ended_at,
                exc_info=sanitized_exc_info,
            )
        except Exception as e:
            sentry_sdk.capture_exception(e)
            current_app.logger.error(f"Error getting job status for job {job_id}: {e}")
            return None

    def get_queue_info(self) -> Optional[QueueInfo]:
        try:
            queue = self.get_queue()
            if not queue:
                return None
            return QueueInfo(
                name=queue.name,
                length=len(queue),
                jobs=[
                    JobInfo(id=job.id, func_name=job.func_name, created_at=job.created_at, status=job.status)
                    for job in queue.jobs
                ],
            )
        except Exception as e:
            sentry_sdk.capture_exception(e)
            current_app.logger.error(f"Error getting queue info: {e}")
            return None

    def retry_failed_job(self, job_id: str) -> JobActionResult:
        try:
            job = Job.fetch(job_id, connection=self.get_redis())
            if job.is_failed:
                job.retry()
                return JobActionResult(status="retried", job_id=job_id)
            else:
                return JobActionResult(status="error", error="Job is not in failed state", job_id=job_id)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            current_app.logger.error(f"Error retrying job {job_id}: {e}")
            return JobActionResult(status="error", error=str(e), job_id=job_id)

    def cancel_job(self, job_id: str) -> JobActionResult:
        try:
            job = Job.fetch(job_id, connection=self.get_redis())
            job.cancel()
            return JobActionResult(status="cancelled", job_id=job_id)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            current_app.logger.error(f"Error cancelling job {job_id}: {e}")
            return JobActionResult(status="error", error=str(e), job_id=job_id)


job_manager = JobManager()
