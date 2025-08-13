from app import create_app
from rq import Worker, Queue

from redis import Redis
import os

# Create the Flask app once
app = create_app()

# Run the worker within the app context
with app.app_context():
    redis_url = app.config.get("REDIS_URL", "redis://localhost:6379/0")
    redis_conn = Redis.from_url(redis_url)

    # Get queue names from environment variable, default to 'default'
    queue_names = os.getenv("RQ_QUEUES", "default").split(",")
    queues = [Queue(name, connection=redis_conn) for name in queue_names]

    worker = Worker(queues, connection=redis_conn)
    worker.work()
