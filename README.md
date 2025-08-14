# CAP Colorado Childcare Portal Backend

This repo is a Flask backend with a Postgres database used for the CAP Colorado Childcare Portal web application.
It also uses Clerk for authentication and Sentry for error tracking.

To get started make a copy of `.env.example` to a `.env` file and populate any keys/values that need to be set.
Download docker and then run `docker-compose up --build -d` and you should be up and running. 

## Examples

Examples of routes can be found under the `app/routes` path. In `app/routes/main.py` you will find
standard non-authenticated routes that can be used for testing. In `app/routes/auth.py` you will find examples
of authenticated routes with used the auth decorators. It is easiest to test these if you have a working
Clerk frontend.


## Useful Commands

### General

#### Build And Start All
```
docker-compose up --build -d
```

#### Start Services (If already built)
```
docker-compose up -d
```

#### View Running Services
```
docker-compose ps
```

#### View Logs of All Services
```
docker-compose logs -f
```

#### View Logs of Specific Service
```
docker-compose logs -f backend
```

#### Stop ad Remove All Services
```
docker-compose down
# To remove volumes (e.g., to reset database data):
# docker-compose down --volumes
```

### Flask

#### Flask Shell
```
docker-compose exec backend flask shell
```

### Migrations

#### Generate New Database Migration
```
docker-compose exec backend flask db migrate -m "Description of your changes"
```

#### Apply All Pending Migrations
```
docker-compose exec backend flask db upgrade
```

#### Database Migration Status
```
docker-compose exec backend flask db history
docker-compose exec backend flask db current
```

#### Revert Last Database Migration
```
docker-compose exec backend flask db downgrade
```

### Containers
```
docker-compose exec backend <command_to_run_inside_container>
```

#### Bash Shell Inside Container
```
docker-compose exec backend /bin/bash
```

#### Clean Up Dangling Images/Volumes
```
docker system prune -a --volumes
```

## Database

### Database shell

To get into a shell for the database itself locally, run:

```
docker-compose exec postgres psql -U dev -d myapp
```

## Job Queue System

This application uses a job queue system to handle background tasks. The system is built on top of Redis, RQ (Redis Queue), and RQ Scheduler. It consists of three main components:

*   **`web`**: The main Flask application. It can enqueue jobs to be processed in the background.
*   **`worker`**: This component listens for jobs on the Redis queue and executes them.
*   **`scheduler`**: This component is responsible for scheduling jobs to be run at a specific time or on a recurring basis.

### The `JobManager`

All job-related functionality is encapsulated in the `JobManager` class, which can be found in `app/jobs/__init__.py`. This class provides a decorator and methods for defining, enqueuing, and scheduling jobs.

### Defining a Job

To define a new job, create a function and decorate it with `@job_manager.job`. This decorator will turn your function into a background job that can be enqueued.

**Example:**

```python
from app.jobs import job_manager

@job_manager.job
def my_background_job(arg1, arg2):
    # Your job logic here
    print(f"Job executed with args: {arg1}, {arg2}")
```

### Enqueuing a Job

To enqueue a job for immediate execution, use the `.delay()` method on the decorated function.

**Example:**

```python
from .jobs.my_job import my_background_job

# This will enqueue the job to be run by a worker as soon as possible
my_background_job.delay("hello", "world")
```

### Scheduling a Job

To schedule a job to be run at a later time, use the `.delay_in()` method. This method takes a `timedelta` object as the first argument.

**Example:**

```python
from datetime import timedelta
from .jobs.my_job import my_background_job

# This will enqueue the job to be run in 1 hour
my_background_job.delay_in(timedelta(hours=1), "hello", "world")
```

To schedule a recurring job, use the `.schedule_cron()` method. This method takes a cron string as the first argument.

**Example:**

```python
from .jobs.my_job import my_background_job

# This will schedule the job to run every day at midnight
my_background_job.schedule_cron("0 0 * * *", "hello", "world")
```

### Job Management API

The application provides a set of API endpoints for managing jobs:

*   **`GET /jobs/<job_id>/status`**: Get the status of a specific job.
*   **`POST /jobs/<job_id>/retry`**: Retry a failed job.
*   **`GET /jobs/queue-info`**: Get information about the job queue, including the number of jobs and their details.
