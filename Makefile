.PHONY: up down logs test lint typecheck check smoke

up:
	./scripts/start.sh

down:
	docker compose down -v

logs:
	docker compose logs -f middleware

test:
	cd middleware && uv run pytest

lint:
	cd middleware && uv run ruff check . && uv run ruff format --check .

typecheck:
	cd middleware && uv run mypy .

check: lint typecheck test

smoke:
	./scripts/smoke.sh
