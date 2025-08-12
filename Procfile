web: gunicorn wsgi:app
worker: rq worker --url $REDIS_URL
scheduler: rqscheduler --url $REDIS_URL