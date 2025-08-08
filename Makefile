GOALS := $(MAKECMDGOALS)
TARGET := $(firstword $(GOALS))
ARGS := $(wordlist 2,$(words $(GOALS)),$(GOALS))
.PHONY: format build logs run down exec db db-shell db-upgrade

format:
	black --line-length 120 . $(ARGS)
build:
	docker compose up --build -d $(ARGS)
logs:
	docker compose logs -f backend --no-log-prefix $(ARGS)
run:
	docker compose up $(ARGS)
down:
	docker compose down $(ARGS)
test:
	docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend pytest $(ARGS)
exec:
	docker compose exec backend $(ARGS)
db:
	docker compose exec backend flask db $(ARGS)
db-shell:
	docker compose exec postgres psql -U dev -d myapp $(ARGS)
db-upgrade:
	docker-compose exec backend flask db upgrade
%:
	@# Do nothing
