from redis import Redis
from rq import Queue
from rq.job import Job
from rq_scheduler import Scheduler
import functools
from flask import current_app

# Redis connection
redis_conn = None
job_queue = None
job_scheduler = None


def init_job_queue(app):
    """Initialize job queue with Flask app"""
    global redis_conn, job_queue, job_scheduler

    redis_url = app.config.get("REDIS_URL", "redis://localhost:6379/0")
    redis_conn = Redis.from_url(redis_url)
    job_queue = Queue(connection=redis_conn)
    job_scheduler = Scheduler(connection=redis_conn)

    app.redis = redis_conn
    app.job_queue = job_queue
    app.job_scheduler = job_scheduler


def get_queue():
    """Get the job queue"""
    return job_queue


def get_scheduler():
    """Get the job scheduler"""
    return job_scheduler


def get_redis():
    """Get redis connection"""
    return redis_conn


def job(func):
    """
    Decorator that:
    1. Ensures Flask app context is available in jobs
    2. Keeps the original function importable by RQ
    3. Provides a clean @job decorator interface
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Only create app context if we don't already have one
        if current_app:
            # We already have app context (probably in a request)
            return func(*args, **kwargs)
        else:
            # We're in a worker process, need to create app context
            from app import create_app
            app = create_app()
            with app.app_context():
                return func(*args, **kwargs)
    
    # Make sure RQ can import this function properly
    wrapper.__name__ = func.__name__
    wrapper.__module__ = func.__module__
    wrapper.__qualname__ = func.__qualname__
    
    # Add a helper method to easily queue this job
    def delay(*args, **kwargs):
        """Queue this job for immediate execution"""
        return get_queue().enqueue(wrapper, *args, **kwargs)
    
    def delay_in(delay, *args, **kwargs):
        """Queue this job for delayed execution"""
        return get_queue().enqueue_in(delay, wrapper, *args, **kwargs)
    
    def schedule_cron(cron_string, *args, **kwargs):
        """Schedule this job with cron syntax"""
        return get_scheduler().cron(cron_string, wrapper, args=args, kwargs=kwargs)
    
    # Attach helper methods to the wrapper
    wrapper.delay = delay
    wrapper.delay_in = delay_in
    wrapper.schedule_cron = schedule_cron
    
    return wrapper


def get_job_status(job_id):
    """Get job status by ID"""
    try:
        job = Job.fetch(job_id, connection=get_redis())
        return {
            "id": job.id,
            "status": job.status,
            "result": job.result,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "ended_at": job.ended_at,
            "exc_info": job.exc_info,
        }
    except Exception as e:
        return {"error": str(e)}


def get_queue_info():
    """Get queue statistics"""
    queue = get_queue()

    if not queue:
        return {"error": "Queue not found"}

    try:
        return {
            "name": queue.name,
            "length": len(queue),
            "jobs": [
                {"id": job.id, "func_name": job.func_name, "created_at": job.created_at, "status": job.status}
                for job in queue.jobs
            ],
        }
    except Exception as e:
        return {"error": str(e)}


def retry_failed_job(job_id):
    """Retry a failed job"""
    try:
        job = Job.fetch(job_id, connection=get_redis())
        if job.is_failed:
            job.retry()
            return {"status": "retried", "job_id": job_id}
        else:
            return {"error": "Job is not in failed state"}
    except Exception as e:
        return {"error": str(e)}


def cancel_job(job_id):
    """Cancel a job"""
    try:
        job = Job.fetch(job_id, connection=get_redis())
        job.cancel()
        return {"status": "cancelled", "job_id": job_id}
    except Exception as e:
        return {"error": str(e)}
