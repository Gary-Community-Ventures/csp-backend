format:
	black --line-length 120 .
build:
	docker compose up --build -d
logs:
	docker compose logs -f backend
run:
	docker compose up
down:
	docker compose down
test:
	docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend pytest
