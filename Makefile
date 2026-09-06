.PHONY: install dev test web-dev web-build docker

install:            ## Install backend deps (dev)
	pip install -e ".[dev]"

dev:                ## Run the API with auto-reload
	uvicorn app.main:app --reload --port 8000

test:               ## Backend tests
	python -m pytest

web-dev:            ## Frontend dev server (proxies /api -> :8000)
	cd web && npm install && npm run dev

web-build:          ## Type-check + build the frontend
	cd web && npm install && npm run build

docker:             ## Build & run the production container
	docker compose up --build
