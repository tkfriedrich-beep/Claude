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

## View on your phone (Tailscale)

The cockpit is local-first, but you can reach it from your phone over a private
[Tailscale](https://tailscale.com) tailnet — no ports opened to the internet.

1. Install Tailscale on the Mac running Otto **and** on your phone; sign both into the same
   account. Note the Mac's name in the Tailscale app (e.g. `toms-imac`) — its full MagicDNS
   name is `toms-imac.<your-tailnet>.ts.net`, or use its `100.x.y.z` tailnet IP.
2. On the Mac, start Otto bound to a reachable interface:
   ```bash
   make phone            # opens the socket on all interfaces, but the API is tailnet-guarded
   # or, hard socket-level tailnet bind (not even listening on your home Wi-Fi):
   make phone PHONE_HOST=100.x.y.z    # your Mac's Tailscale IP
   ```
3. On your phone's browser, open **`http://toms-imac.<your-tailnet>.ts.net:3000`**
   (or `http://100.x.y.z:3000`). That's it — the UI derives the control-plane URL from the
   host you loaded, and CORS already allows tailnet origins, so no per-device config is needed.

**Security:** the control plane stays single-user and unauthenticated, so a **network guard**
(`cockpit/netguard.py`) is the access boundary: it answers **localhost + your Tailscale tailnet
only** (`100.64.0.0/10`). A random host on the same Wi-Fi that reaches the port gets `403` — CORS
can't stop a non-browser client, but the guard can. `make phone` on `0.0.0.0` is therefore safe
by default; `PHONE_HOST=<tailscale-ip>` additionally stops the socket from even listening on
Wi-Fi. To deliberately allow a trusted LAN, set `COCKPIT_TRUSTED_NETWORKS` (comma-separated
CIDRs; `"0.0.0.0/0,::/0"` allows all). Keep **Safe Mode ON** regardless (external writes stay
blocked; every action is still approval-gated). Do **not** run `tailscale funnel` on these ports
— that would publish Otto to the public internet. For HTTPS with a real cert, `tailscale serve`
is an option but needs both ports proxied under one name (out of scope here).

## Operational safety

- **Safe Mode** (Settings or home header) blocks all external writes regardless of skill config.
- **Kill switch** halts the worker — nothing executes until released.
- Approvals expire (default 24 h). Denials are terminal for that proposal.
- Logs: structured JSON on the control-plane stdout; secrets are redacted; raw payloads only
  behind explicit "Technical details" expansion in the UI.
