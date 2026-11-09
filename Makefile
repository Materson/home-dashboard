.DEFAULT_GOAL := help

help:
	@echo "Common targets:"
	@echo "  make backend    - start Django dev server"
	@echo "  make worker     - start a Celery worker"
	@echo "  make beat       - start Celery beat"
	@echo "  make frontend   - start the Vite dev server"
	@echo "  make test       - run pytest"
	@echo "  make lint       - ruff check + format"
	@echo "  make gen-api    - regenerate the frontend API types"
	@echo "  make up         - docker compose up -d"
	@echo "  make down       - docker compose down"

backend:
	cd backend && uv run python manage.py runserver 0.0.0.0:8000

worker:
	cd backend && uv run celery -A config worker -l info

beat:
	cd backend && uv run celery -A config beat -l info

frontend:
	cd frontend && npm run dev

test:
	cd backend && uv run pytest

lint:
	cd backend && uv run ruff check . && uv run ruff format .

gen-api:
	cd frontend && npm run gen:api

up:
	docker compose up -d --build

down:
	docker compose down
