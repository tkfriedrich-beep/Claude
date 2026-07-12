# CLAUDE.md — working on AgenticOS Cockpit

Read `BUILD_BRIEF.md` first; it is the governing product/architecture/security brief.
`DECISIONS.md` records every deviation. `PROGRESS.md` records milestone state and real test results.

## Commands

- `make setup` / `make dev` / `make test` / `make e2e` / `make lint` / `make doctor` / `make demo`
- Control plane only: `cd services/control-plane && uv run pytest -q`
- Web only: `cd apps/web && pnpm test` (vitest) / `pnpm build` / `pnpm lint`
- Regenerate TS API types after changing FastAPI routes: `make contracts`

## Architecture invariants (do not weaken silently — see BUILD_BRIEF.md for the full list)

1. `apps/web` never imports Anthropic/OpenAI/connector SDKs; it only calls `/api/v1`.
2. Skills never call third-party APIs; they call typed tools through the Tool Gateway
   (`cockpit/gateway.py`).
3. Only the Policy Gateway (`cockpit/policy.py`) decides whether an action is allowed —
   never a connector, never a prompt.
4. Provider events are normalized (`cockpit/events.py`) before reaching the UI.
5. Prompts are versioned files under `skills/*/prompts/`; policies are deterministic code.
6. Every external mutation gets an idempotency key and records its confirmation.
7. Every table carries `workspace_id`; the MVP stays single-user/local.
8. Run state changes go through the FSM in `cockpit/state_machine.py` — never set
   `run.status` directly.

## Layout

- `services/control-plane/src/cockpit/` — config, db, models, schemas, events, state_machine,
  policy, gateway, worker, `connectors/`, `skills/`, `runtime/`, `api/`
- `services/control-plane/tests/` — pytest (policy, FSM, gateway, skills, API)
- `apps/web/src/` — `app/` routes, `components/ui/` design system, `components/cockpit/`,
  `lib/` (api client, sse, hooks)
- `skills/<id>/` — `manifest.yaml`, `SKILL.md`, `input.schema.json`, `output.schema.json`,
  `prompts/`, `fixtures/`
- `connectors/<id>/` — `manifest.yaml`, `README.md`; Python impl in
  `services/control-plane/src/cockpit/connectors/`

## Conventions

- Python: 3.12, fully typed, async SQLAlchemy; `ruff` + `mypy` clean; pytest-asyncio for async tests.
- TypeScript: strict; API types come from `packages/contracts` (generated — do not hand-edit
  `api.d.ts`).
- Never log or commit secrets; use `SecretStore` (env-based) and the log redactor.
- Every new tool needs a manifest entry with risk level, schemas, timeout, and approval policy —
  the gateway rejects unmanifested tools.
- Demo data must be clearly labeled `demo` in both API payloads and UI.
- After schema changes: `cd services/control-plane && uv run alembic revision --autogenerate` +
  review the migration; never edit applied migrations.
