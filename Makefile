format:
	black --line-length 120 .
test:
	docker-compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend pytest
