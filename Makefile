format:
	black --line-length 120 .
build:
	docker compose up --build -d
logs:
	docker compose logs -f
run:
	docker compose up
down:
	docker compose down
