web: gunicorn wsgi:app
worker: rq worker --url $REDIS_URL
scheduler: python scheduler.py