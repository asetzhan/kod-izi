COMPOSE := docker compose -f infra/docker-compose.yml --env-file .env
BACKEND := $(COMPOSE) run --rm backend
FRONTEND := $(COMPOSE) run --rm --no-deps frontend

.PHONY: help env dev down logs migrate seed create-admin test test-backend test-frontend lint

help:
	@echo "make dev           - start all services (http://localhost:$${HTTP_PORT:-8080})"
	@echo "make down          - stop all services"
	@echo "make logs          - follow service logs"
	@echo "make migrate       - apply Alembic migrations"
	@echo "make seed          - demo accounts for local development (APP_ENV=dev only)"
	@echo "make create-admin EMAIL=you@example.com - create the first administrator"
	@echo "make test          - backend and frontend tests"
	@echo "make lint          - ruff, mypy, bandit, eslint, tsc"

env:
	@sh infra/scripts/init-env.sh

dev: env
	$(COMPOSE) up --build -d
	@echo "Open http://localhost:$$(grep -E '^HTTP_PORT=' .env | cut -d= -f2)"

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

migrate: env
	$(BACKEND) alembic upgrade head

seed: env
	$(BACKEND) python -m app.cli seed-demo

create-admin: env
	@test -n "$(EMAIL)" || (echo "Usage: make create-admin EMAIL=you@example.com" && exit 1)
	$(BACKEND) python -m app.cli create-admin --email "$(EMAIL)"

test: test-backend test-frontend

test-backend: env
	$(BACKEND) pytest

test-frontend: env
	$(FRONTEND) npm test

lint: env
	$(BACKEND) sh -c "ruff format --check . && ruff check . && mypy app tests && bandit -q -c pyproject.toml -r app"
	$(FRONTEND) sh -c "npm run lint && npm run typecheck"
