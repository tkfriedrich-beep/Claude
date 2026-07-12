# DECISIONS.md — Architecture Decision Records

Each entry: context → decision → consequences. Newest last. Deviations from `BUILD_BRIEF.md`
are explicitly flagged **[deviation]**.

---

## ADR-001 — Commit and push to the designated branch, open a draft PR **[deviation]**

- **Context:** BUILD_BRIEF.md says "Do not push to a remote repository … unless explicitly
  instructed." The session that launched this build explicitly instructs developing on
  `claude/build-brief-implementation-dbre2i`, committing, pushing, and opening a draft PR.
- **Decision:** The session instruction is the more specific, later instruction from the owner;
  push to that branch only. No deploys.
- **Consequences:** Work is reviewable as a draft PR. Nothing is deployed anywhere.

## ADR-002 — `packages/ui` deferred; components live in `apps/web` **[deviation]**

- **Context:** The brief's repo shape lists `packages/ui`. There is exactly one web app in the MVP.
- **Decision:** Keep the design system in `apps/web/src/components/ui` and defer the shared
  package until a second surface (e.g. Tauri wrapper) exists. `packages/contracts` is kept.
- **Consequences:** Less indirection now; extracting later is mechanical because components
  depend only on Tailwind tokens and React.

## ADR-003 — Connector code in control plane; manifests in `connectors/`

- **Context:** The brief shows `connectors/` at repo root; the control plane (Python) must import
  connector implementations.
- **Decision:** `connectors/<id>/manifest.yaml` + README are the connector *definitions* (loaded
  at startup); the Python implementation classes live in
  `services/control-plane/src/cockpit/connectors/`. Same pattern as `skills/`.
- **Consequences:** Repo shape matches the brief; code stays importable and typed; a future
  out-of-process connector host can consume the same manifests.

## ADR-004 — The `runs` table is the persistent jobs table

- **Context:** Brief requires "a persistent jobs table and lightweight in-process worker loop;
  no mandatory Redis."
- **Decision:** Queued runs *are* the jobs: the async worker polls `runs` with
  `status='queued'`, claims via an atomic compare-and-swap on `worker_claim`, and executes.
  Schedules materialize future runs. No separate jobs table.
- **Consequences:** One less table to keep consistent; run history and job history are the same
  audit trail. If multi-process workers arrive later, claiming already uses CAS semantics.

## ADR-005 — Initial Alembic migration is generated from model metadata

- **Context:** 20+ tables at project start; hand-writing the first migration adds no safety.
- **Decision:** `0001_initial` is produced by Alembic autogenerate from `cockpit/models.py`
  (plus raw SQL for the FTS5 virtual table and WAL pragma) and reviewed. All later migrations
  are proper deltas. Downgrade of `0001` drops the schema.
- **Consequences:** Models are the single source of truth at bootstrap; normal Alembic
  discipline applies from `0002` on.

## ADR-006 — Async SQLAlchemy + aiosqlite; CORS instead of a dev proxy

- **Decision:** Control plane is fully async (FastAPI + SQLAlchemy 2 async + aiosqlite), which
  keeps SSE, the worker loop, and the scheduler in one event loop. The web app calls
  `http://localhost:8787` directly with CORS restricted to localhost origins — reliable for
  `EventSource`, no Next.js proxy buffering concerns.
- **Consequences:** One process, no thread pools for DB; deployment behind a shared origin later
  just tightens CORS.

## ADR-007 — Deterministic-first skills; LLM enhancement is optional

- **Context:** Demo mode must be useful without credentials; "no false success."
- **Decision:** Project Pulse, Business Idea Triage, Morning Brief, Daily Plan, Weekly Review and
  Commitment Sweep produce their results deterministically from local data. Decision Memo (and
  others where marked) call the configured `AgentRuntime` for analysis when a provider is
  healthy, otherwise fall back to a structured deterministic template. Every artifact records
  `generation_mode: deterministic | llm_assisted` and the provider used.
- **Consequences:** Tests are deterministic; credential-less demo is honest; LLM value is
  additive, not load-bearing.

## ADR-008 — Chat sessions ride the same run pipeline

- **Decision:** A Command-screen conversation is a `provider_sessions` row; each user turn is a
  `run` (kind `chat`) linked to it. Interrupt/cancel/resume act on the active run; resume uses
  the stored external provider session id. Skill runs (kind `skill`) share the same FSM, events,
  approvals, and history.
- **Consequences:** One audit model for everything the system does; History shows chat turns and
  skill runs uniformly.

## ADR-009 — Tailwind CSS v4 with CSS-first design tokens

- **Decision:** Use Tailwind v4 (`@import "tailwindcss"` + `@theme`) — current stable — and
  define the warm-parchment/midnight token palette as CSS variables consumed by `@theme`,
  giving runtime theme switching via `data-theme` without a JS styling layer.
- **Consequences:** Design tokens live in exactly one file (`app/globals.css`).

## ADR-010 — Hand-rolled accessible primitives instead of stock shadcn/radix

- **Context:** Brief asks for shadcn/ui primitives "customized into a coherent design system
  rather than left looking like stock components"; the MVP needs ~12 primitives.
- **Decision:** Implement a small shadcn-inspired component set (Button, Card, Badge, Dialog,
  Sheet, Tabs, Switch, Input, …) directly with Tailwind + cva and explicit keyboard/ARIA
  behavior, rather than pulling the full Radix dependency tree.
- **Consequences:** Full control of styling and motion; the burden of a11y correctness is ours —
  covered by axe checks + keyboard e2e tests.

## ADR-011 — Shell execution is not exposed as a runtime tool in the MVP **[tightening]**

- **Context:** Brief allows workspace-restricted shell with approval.
- **Decision:** Stronger default: no shell tool in the runtime tool manifest at all. The Claude
  chat session gets read-only file tools within configured roots; writes go through the
  local-files connector with approval. A future shell wrapper would enter as its own connector
  with R3/R4 classification.
- **Consequences:** Smaller attack surface; some power-user tasks impossible until that
  connector exists. Recorded as tightening, not weakening.

## ADR-012 — SSE keeps one global stream + per-run streams

- **Decision:** `/api/v1/events/stream` (global, powers the activity rail and approval badge)
  and `?run_id=` filtered streams (power the run timeline). Events are persisted first in
  `run_events`, then published in-process; `Last-Event-ID`/`since` backfills from the table, so
  a dropped connection never loses events.
- **Consequences:** The UI can always reconstruct state from the DB; live updates are an
  optimization, not a source of truth.
