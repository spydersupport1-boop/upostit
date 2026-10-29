# Attendance SaaS Makefile

.PHONY: help up down test lint clean verify-db celery-smoke

PYTHON := python3
VENV_BIN := .venv/bin

help:
	@echo "Attendance SaaS Management Commands"
	@echo "======================================"
	@echo "  make up           Start local Redis and MinIO services (Docker Compose)"
	@echo "  make down         Stop local Docker services"
	@echo "  make test         Execute automated backend test suite (pytest)"
	@echo "  make lint         Run code linter (ruff) and type checker (mypy)"
	@echo "  make verify-db    Safely test connection to Supabase PostgreSQL and PostGIS"
	@echo "  make celery-smoke Run Celery worker configuration smoke test"
	@echo "  make clean        Remove cache and temporary build files"

up:
	docker compose -f infra/docker-compose.yml up -d

down:
	docker compose -f infra/docker-compose.yml down

test:
	$(VENV_BIN)/pytest tests/ -v

lint:
	$(VENV_BIN)/ruff check services/ packages/ tests/
	$(VENV_BIN)/mypy services/api/

verify-db:
	$(VENV_BIN)/python services/api/verify_db.py

celery-smoke:
	$(VENV_BIN)/python services/workers/smoke_test.py

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache
