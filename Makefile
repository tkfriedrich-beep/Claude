# AgenticOS Cockpit — top-level commands. See docs/RUNBOOK.md.
SHELL := /bin/bash
CP := services/control-plane
WEB := apps/web

.PHONY: setup dev phone demo test e2e lint format doctor contracts clean app

setup: ## Install all dependencies and migrate the local database
	cd $(CP) && uv sync --extra dev
	cd $(CP) && uv run alembic upgrade head   # migrate first so a web-deps hiccup can't leave the DB unmigrated
	pnpm install

dev: ## Run control plane (:8787) and web (:3000) together (localhost only)
	@trap 'kill 0' EXIT; \
	( cd $(CP) && uv run uvicorn cockpit.main:app --port 8787 --reload ) & \
	( cd $(WEB) && pnpm dev ) & \
	wait

# Bind both servers to a reachable interface so you can open the cockpit on your phone over
# Tailscale (or your LAN). Default 0.0.0.0 = all interfaces (LAN + tailnet + localhost). For
# tailnet-ONLY, pass your Tailscale IP: `make phone PHONE_HOST=100.x.y.z`. The unauthenticated
# API is now reachable to anything that can reach this machine — keep Safe Mode ON, and never
# `tailscale funnel` this (that would expose it to the public internet).
PHONE_HOST ?= 0.0.0.0
phone: ## Serve on all interfaces for phone/Tailscale access (PHONE_HOST=100.x.y.z for tailnet-only)
	@echo "▶ Cockpit reachable at http://<this-machine's-tailscale-name>:3000 (bind $(PHONE_HOST))"
	@echo "  Keep Safe Mode ON. Do NOT run 'tailscale funnel' — that publishes to the internet."
	@trap 'kill 0' EXIT; \
	( cd $(CP) && uv run uvicorn cockpit.main:app --host $(PHONE_HOST) --port 8787 --reload ) & \
	( cd $(WEB) && pnpm exec next dev --port 3000 --hostname $(PHONE_HOST) ) & \
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

app: ## Rebuild both Otto launcher icons and mark the launchers executable
	uv run --with pillow python desktop/make_icon.py --variant default
	uv run --with pillow python desktop/make_icon.py --variant phone
	chmod +x desktop/Otto.app/Contents/MacOS/Otto "desktop/Otto (Phone).app/Contents/MacOS/Otto Phone"
	@echo "Otto.app (local, indigo) + 'Otto (Phone).app' (Tailscale, gold) ready — drag to your Desktop; right-click → Open the first time."

clean: ## Remove build artifacts (keeps data/local)
	rm -rf $(WEB)/.next $(WEB)/node_modules node_modules $(CP)/.venv
