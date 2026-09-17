.PHONY: dev test test-all lint security frontend api-docs build docker docker-up docker-down

# Development
dev:
	docker compose up -d postgres
	@echo "Postgres started. Run 'poetry run karr migrate up && poetry run karr serve' and 'cd frontend && npm run dev'"

# Tests: unit + contract (no database), and the whole suite against TEST_DATABASE_URL
test:  # what CI's `test` matrix runs, plus the contract fixture checks
	poetry run pytest tests/unit tests/contract

test-all:
	poetry run pytest tests --cov=karr

# Code quality
lint:
	poetry run ruff check src tests scripts
	poetry run ruff format --check src tests scripts
	poetry run mypy

security:  # the same invocations as CI's `security` job
	poetry run bandit -c pyproject.toml -r src scripts
	poetry run pip-audit

# Frontend: build and install into the package's static dir
frontend:
	cd frontend && npm ci && npm run lint && npm run typecheck && npm test -- --run && npm run build
	rm -rf src/karr/web/static/assets
	cp -r frontend/dist/. src/karr/web/static/

# Regenerate docs/api.md from the OpenAPI schema
api-docs:
	poetry run python scripts/gen_api_docs.py > docs/api.md.tmp && mv docs/api.md.tmp docs/api.md

# Build
build: frontend
	poetry build

# Docker
docker:
	docker compose build

docker-up:
	docker compose up

docker-down:
	docker compose down
