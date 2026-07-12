# AgenticOS Cockpit — top-level commands. See docs/RUNBOOK.md.
SHELL := /bin/bash
CP := services/control-plane
WEB := apps/web

.PHONY: setup dev demo test e2e lint format doctor contracts clean

setup: ## Install all dependencies and migrate the local database
	cd $(CP) && uv sync --extra dev
	pnpm install
	cd $(CP) && uv run alembic upgrade head

dev: ## Run control plane (:8787) and web (:3000) together
	@trap 'kill 0' EXIT; \
	( cd $(CP) && uv run uvicorn cockpit.main:app --port 8787 --reload ) & \
	( cd $(WEB) && pnpm dev ) & \
	wait

demo: ## Seed the demo workspace (idempotent)
	cd $(CP) && uv run python -m cockpit.demo

test: ## Unit + integration tests (pytest + vitest)
	cd $(CP) && uv run pytest -q
	cd $(WEB) && pnpm test -- --run

e2e: ## Playwright end-to-end tests (starts both servers itself)
	cd $(WEB) && pnpm exec playwright test

lint: ## ruff + mypy + eslint + tsc
	cd $(CP) && uv run ruff check src tests && uv run ruff format --check src tests
	cd $(CP) && uv run mypy src
	cd $(WEB) && pnpm lint && pnpm typecheck

format: ## Auto-format everything
	cd $(CP) && uv run ruff format src tests && uv run ruff check --fix src tests
	cd $(WEB) && pnpm lint --fix || true

doctor: ## Diagnose environment and configuration
	cd $(CP) && uv run python -m cockpit.doctor

contracts: ## Regenerate packages/contracts from the FastAPI OpenAPI schema
	cd $(CP) && uv run python -m cockpit.export_openapi ../../packages/contracts/openapi.json
	pnpm --filter @agenticos/contracts generate

clean: ## Remove build artifacts (keeps data/local)
	rm -rf $(WEB)/.next $(WEB)/node_modules node_modules $(CP)/.venv
