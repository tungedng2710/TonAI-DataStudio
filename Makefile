.PHONY: install dev-api dev-web test lint build compose-up compose-web compose-down migrate

install:
	uv pip install -e '.[dev]'
	cd apps/web && npm ci

dev-api:
	uvicorn data_studio_api.main:app --reload --port 8000

dev-web:
	cd apps/web && npm run dev

test:
	pytest
	cd apps/web && npm test

lint:
	ruff check apps/api tests migrations
	ruff format --check apps/api tests migrations
	mypy apps/api/data_studio_api
	cd apps/web && npm run lint

build:
	cd apps/web && npm run build

migrate:
	alembic upgrade head

compose-up:
	docker compose --env-file .env -f infrastructure/docker-compose.yml up -d --build

compose-web:
	docker compose --env-file .env -f infrastructure/docker-compose.yml up -d --no-deps --build web

compose-down:
	docker compose --env-file .env -f infrastructure/docker-compose.yml down
