COMPOSE := docker compose -f infra/docker-compose.yml --env-file .env
BACKEND := $(COMPOSE) run --rm backend
FRONTEND := $(COMPOSE) run --rm --no-deps frontend

.PHONY: help env dev down logs migrate seed create-admin test test-backend test-frontend lint llm backup retention train-dkt

help:
	@echo "make dev           - start all services (http://localhost:$${HTTP_PORT:-8080})"
	@echo "make down          - stop all services"
	@echo "make logs          - follow service logs"
	@echo "make migrate       - apply Alembic migrations"
	@echo "make seed          - course catalogue and draft tasks (+ demo accounts in dev)"
	@echo "make create-admin EMAIL=you@example.com - create the first administrator"
	@echo "make test          - backend and frontend tests"
	@echo "make lint          - ruff, mypy, bandit, eslint, tsc"
	@echo "make llm           - start the local LLM (Ollama) and download its models"
	@echo "make backup        - make an encrypted backup now"
	@echo "make retention     - anonymize data past the retention period (spec 14.3)"
	@echo "make train-dkt COURSE=N - train Code-DKT for a course, compare with BKT (ФТ-40)"

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
	$(BACKEND) python -m app.cli seed

create-admin: env
	@test -n "$(EMAIL)" || (echo "Usage: make create-admin EMAIL=you@example.com" && exit 1)
	$(BACKEND) python -m app.cli create-admin --email "$(EMAIL)"

llm: env
	$(COMPOSE) --profile llm up -d ollama
	$(COMPOSE) exec ollama ollama pull $${OLLAMA_CHAT_MODEL:-llama3.1:8b}
	$(COMPOSE) exec ollama ollama pull $${OLLAMA_EMBED_MODEL:-bge-m3}
	@echo "Set LLM_PROVIDER=ollama in .env and run make dev"

backup: env
	$(COMPOSE) --profile backup run --rm backup backup.sh

retention: env
	$(BACKEND) python -m app.cli retention

# ФТ-40 (Q-19): the `trainer` image has PyTorch (CPU); the model goes to the `models` volume.
train-dkt: env
	@case "$(COURSE)" in ''|*[!0-9]*) echo "usage: make train-dkt COURSE=<course id>"; exit 1;; esac
	$(COMPOSE) --profile ml run --rm trainer python -m app.cli train-dkt --course-id "$(COURSE)" --report /data/models/course-$(COURSE)/report.md

test: test-backend test-frontend

test-backend: env
	$(BACKEND) pytest

test-frontend: env
	$(FRONTEND) npm test

lint: env
	$(BACKEND) sh -c "ruff format --check . && ruff check . && mypy app tests && bandit -q -c pyproject.toml -r app"
	$(FRONTEND) sh -c "npm run lint && npm run typecheck"
