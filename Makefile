.PHONY: help install dev test lint typecheck eval frontend-install frontend-build storefront-install storefront storefront-build build docker

help:
	@echo "Fixpoint targets:"
	@echo "  make install            Install backend dev dependencies"
	@echo "  make dev                Run the API with reload on :8000"
	@echo "  make test               Run backend tests (pytest)"
	@echo "  make lint               Lint the backend (ruff)"
	@echo "  make typecheck          Typecheck backend (mypy) and frontends (tsc)"
	@echo "  make eval               Run the S1-S16 evaluation matrix"
	@echo "  make frontend-install   Install operator console dependencies"
	@echo "  make frontend-build     Build the SPA into frontend/dist"
	@echo "  make storefront-install Install demo storefront dependencies"
	@echo "  make storefront         Run the demo storefront on :5174 (proxies to :8000)"
	@echo "  make storefront-build   Typecheck + build the demo storefront"
	@echo "  make build              Build the production Docker image"
	@echo "  make docker             Run Postgres + API with docker compose"

install:
	cd backend && python -m pip install -r requirements-dev.txt

dev:
	cd backend && python -m alembic upgrade head && python -m uvicorn app.main:app --reload --port 8000

test:
	cd backend && python -m pytest -q

lint:
	cd backend && python -m ruff check .

typecheck:
	cd backend && python -m mypy app
	cd frontend && npm run typecheck
	cd storefront && npm run typecheck

eval:
	cd backend && python -m app.evals.runner

frontend-install:
	cd frontend && npm install --no-audit --no-fund

frontend-build:
	cd frontend && npm run build

storefront-install:
	cd storefront && npm install --no-audit --no-fund

storefront:
	cd storefront && npm run dev

storefront-build:
	cd storefront && npm run build

build:
	docker build -t fixpoint .

docker:
	docker compose up --build
