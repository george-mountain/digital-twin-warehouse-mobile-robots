.PHONY: build up down restart logs ps test clean

build:
	docker compose up --build -d

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f --tail=200

ps:
	docker compose ps

test:
	python -m unittest discover -s tests -v

clean:
	docker compose down --rmi local --remove-orphans
