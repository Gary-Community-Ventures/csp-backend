from redis import Redis
from rq import Queue
from rq.job import Job
from rq_scheduler import Scheduler

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


# Job decorators and utilities
def job(f):
    """Decorator to ensure jobs run with Flask app context"""

    def wrapper(*args, **kwargs):
        # Import your app factory - adjust this path to match your structure
        from app import create_app  # or from .. import create_app if needed
        app = create_app()
        with app.app_context():
            return f(*args, **kwargs)
    
    # Important: Set these attributes so RQ can properly serialize the function
    wrapper.__name__ = f.__name__
    wrapper.__module__ = f.__module__
    wrapper.__qualname__ = f.__qualname__
    
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
