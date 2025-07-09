# Backend Template

This repo is a a template for a Flask backend with a Postgres database. 
It also uses Clerk for authentication and Sentry for error tracking.

To get started make a copy of `.env.example` to a `.env` file and populate any keys/values that need to be set.
Then run `docker-compose up --build -d` and you should be up and running. 

Any changes you make to python files should be hot reloaded for faster development. 

## Examples

Examples of routes can be found under the `app/routes` path. In `app/routes/main.py` you will find
standard non-authenticated routes that can be used for testing. In `app/routes/auth.py` you will find examples
of authenticated routes with used the auth decorators. It is easiest to test these if you have a working
Clerk frontend.


## Useful Commands

### General

#### Build Ad Start All
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