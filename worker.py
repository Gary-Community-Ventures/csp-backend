import os

from rq import Queue, Worker

from app import create_app
from app.utils.redis import create_redis_connection

# Create the Flask app once
app = create_app()

# Run the worker within the app context
with app.app_context():
    redis_url = app.config.get("REDIS_URL", "redis://localhost:6379/0")
    redis_conn = create_redis_connection(redis_url)

    # Get queue names from environment variable, default to 'default'
    queue_names = os.getenv("RQ_QUEUES", "default").split(",")
    queues = [Queue(name, connection=redis_conn) for name in queue_names]

    worker = Worker(queues, connection=redis_conn)
    worker.work()
