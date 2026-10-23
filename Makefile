SHELL := /bin/sh

ifeq ($(OS),Windows_NT)
PY := .venv/Scripts/python.exe
else
PY := .venv/bin/python
endif
NPM ?= npm

.PHONY: help install dev backend frontend samples test test-backend test-frontend e2e lint build check demo seed eval docker-up docker-down docker-logs

help:
	@echo "ClipMind targets"
	@echo "  make install       Create .venv, install backend + frontend dependencies"
	@echo "  make dev           Run backend :8000 and frontend :3000 together"
	@echo "  make backend       Run only the FastAPI server"
	@echo "  make frontend      Run only the Next.js dev server"
	@echo "  make samples       Regenerate bundled demo media + transcripts"
	@echo "  make test          Backend pytest + frontend lint/typecheck"
	@echo "  make e2e           Playwright smoke test (servers must be running)"
	@echo "  make check         Lint, tests, and production frontend build"
	@echo "  make demo          Create and run the bundled demo through the API"
	@echo "  make seed          Seed brand profiles and a completed demo project"
	@echo "  make eval          Run the 81-check acceptance eval"
	@echo "  make docker-up     Build and start the Docker Compose stack"
	@echo "  make docker-down   Stop the Compose stack"

install:
	python -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e "./backend[dev]"
	cd frontend && $(NPM) ci
	cd frontend && npx playwright install chromium

dev:
	$(PY) scripts/dev.py

backend:
	cd backend && ../$(PY) -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

frontend:
	cd frontend && $(NPM) run dev

samples:
	$(PY) scripts/generate_samples.py

test: test-backend test-frontend

test-backend:
	cd backend && ../$(PY) -m pytest -q

test-frontend:
	cd frontend && $(NPM) run typecheck
	cd frontend && $(NPM) run lint

e2e:
	cd frontend && $(NPM) run test:e2e

lint:
	cd backend && ../$(PY) -m ruff check app tests ../scripts

build:
	cd frontend && $(NPM) run build

check: lint test build

demo:
	$(PY) scripts/demo.py

seed:
	$(PY) scripts/seed_demo.py --with-project --wait

eval:
	$(PY) scripts/eval.py

docker-up:
	docker compose up --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f
