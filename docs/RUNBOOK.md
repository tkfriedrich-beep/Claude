# RUNBOOK.md

## Prerequisites

- Node ≥ 20 + pnpm ≥ 9 (`corepack enable` provides pnpm)
- Python ≥ 3.12 + `uv` (https://docs.astral.sh/uv/) — fallback below
- GNU make. No Docker/Redis/Postgres required.

## Daily operation

```bash
make setup      # pnpm install + uv sync + alembic upgrade head
make demo       # seed demo workspace/data (idempotent, safe to re-run)
make dev        # control plane :8787 + web :3000 (Ctrl-C stops both)
make doctor     # diagnose environment/config; every failure prints its fix
make test       # pytest + vitest
make e2e        # Playwright (boots both servers itself)
make lint       # ruff + mypy + eslint + tsc --noEmit
make contracts  # regenerate packages/contracts from the live OpenAPI schema
```

Run services individually:

```bash
cd services/control-plane && uv run uvicorn cockpit.main:app --port 8787 --reload
cd apps/web && pnpm dev
```

### Without uv (fallback)

```bash
cd services/control-plane
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn cockpit.main:app --port 8787
```

## Configuration

Environment (see `.env.example`; load via `services/control-plane/.env`):

| Var | Meaning | Default |
| --- | --- | --- |
| `COCKPIT_DATA_DIR` | SQLite + artifacts location | `<repo>/data/local` |
| `COCKPIT_PORT` | control plane port | `8787` |
| `ANTHROPIC_API_KEY` | enables Claude runtime (or authenticated `claude` CLI) | unset → mock/demo |
| `COCKPIT_SAFE_MODE_DEFAULT` | Safe Mode on first boot | `true` |
| `COCKPIT_N8N_SECRET_<NAME>` | HMAC secret for a registered n8n webhook | — |

Paths to your Obsidian vault and bizideas folder are set during onboarding (Settings →
Storage afterwards). Read access only until you approve writes.

## Data, backup, export

- DB: `data/local/cockpit.db` (SQLite WAL — copy all `cockpit.db*` files together)
- Artifacts: `data/local/artifacts/<run_id>/…` (plain Markdown/JSON)
- Backup = stop the app, copy `data/local/`. Restore = put it back.
- Export: Settings → Storage → Export, or `GET /api/v1/memories/export`,
  `GET /api/v1/artifacts/{id}/download`.
- Full reset: delete `data/local/` then `make setup && make demo`.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `make doctor` reports missing uv/pnpm | install per Prerequisites; doctor prints exact commands |
| Port 8787/3000 in use | `lsof -i :8787` and stop the process, or set `COCKPIT_PORT` + `NEXT_PUBLIC_API_URL` |
| Web shows "control plane unreachable" | start `make dev`; check `curl localhost:8787/api/v1/health` |
| Claude provider "unavailable" | set `ANTHROPIC_API_KEY` or authenticate `claude` CLI; then Integrations → Claude → Check health |
| Runs stuck `interrupted` after crash/restart | expected: worker marks in-flight runs interrupted on boot; use Resume/Restart in History (no external write re-fires — idempotency keys) |
| Stale/expired approval | expired approvals cannot execute; re-run the skill to get a fresh proposal |
| DB migration error mid-upgrade | `cp -r data/local data/local.bak` then `uv run alembic upgrade head`; if corrupted, restore backup or full reset |
| Playwright wants to download browsers | don't; Chromium is preinstalled (`PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers` in CI/sandbox) |
| SSE not updating behind a proxy | use direct localhost; proxies must not buffer `text/event-stream` |

## Operational safety

- **Safe Mode** (Settings or home header) blocks all external writes regardless of skill config.
- **Kill switch** halts the worker — nothing executes until released.
- Approvals expire (default 24 h). Denials are terminal for that proposal.
- Logs: structured JSON on the control-plane stdout; secrets are redacted; raw payloads only
  behind explicit "Technical details" expansion in the UI.
