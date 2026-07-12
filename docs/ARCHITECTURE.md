# ARCHITECTURE.md

## System shape

A two-process local system plus static definitions:

```
apps/web  (Next.js 15, TS, Tailwind v4, TanStack Query, SSE)   ── http://localhost:3000
   │  fetch/EventSource, typed by packages/contracts (OpenAPI-generated)
   ▼
services/control-plane  (FastAPI, Python 3.12, async SQLAlchemy) ── http://localhost:8787
   ├─ api/          versioned routers under /api/v1
   ├─ worker        in-process async run executor (runs table = job queue, ADR-004)
   ├─ scheduler     materializes due schedules into runs (Shadow Mode aware)
   ├─ gateway       Typed Tool Gateway + Policy & Approval Gateway
   ├─ runtime/      AgentRuntime interface: claude | mock (openai/ollama/langgraph stubs)
   ├─ connectors/   local_files, obsidian, n8n, mcp, + mock google/notion/github
   └─ SQLite (WAL) + FTS5 at data/local/cockpit.db, artifacts at data/local/artifacts/
skills/*      versioned runtime skill definitions (manifest, schemas, prompts, fixtures)
connectors/*  connector manifests + docs (implementations live in the control plane, ADR-003)
```

Canonical flow (must not be short-circuited):

```
User → Cockpit UI → Command API → Intent/Triage Router → one Skill → Plan
     → Policy + Approval Gateway → Agent Runtime → Typed Tool Gateway
     → Connector → Tool Result → Verification → Quality Review
     → Human-readable result + artifacts + audit events
```

## Control plane modules

| Module | Responsibility |
| --- | --- |
| `cockpit/config.py` | pydantic-settings; data dir, ports, roots, safe-mode default, budgets |
| `cockpit/db.py` | async engine/session, WAL pragmas |
| `cockpit/models.py` | SQLAlchemy models — all tables carry `workspace_id` |
| `cockpit/schemas.py` | Pydantic API models; OpenAPI source of truth |
| `cockpit/events.py` | normalized event types, in-process bus, persistence, human_text |
| `cockpit/state_machine.py` | run FSM; the only writer of `run.status` |
| `cockpit/policy.py` | risk model R0–R4, autonomy 0–5, deterministic `evaluate()` |
| `cockpit/gateway.py` | tool manifests, schema validation, policy check, approvals, idempotency, execution, confirmation recording |
| `cockpit/secrets.py` | `SecretStore` abstraction (env-backed for local web) |
| `cockpit/logging.py` | structured JSON logs with redaction |
| `cockpit/registry/` | skill + connector registries (load manifests from repo dirs) |
| `cockpit/skills/` | skill executors (deterministic-first, ADR-007) |
| `cockpit/runtime/` | `AgentRuntime` protocol + adapters |
| `cockpit/worker.py` | claim → pipeline (triage→plan→policy→approval→execute→verify→review) |
| `cockpit/scheduler.py` | due schedules → runs; Shadow Mode |
| `cockpit/api/` | routers: health/doctor, onboarding, commands, runs, events(SSE), approvals, skills, connectors, automations, artifacts, memories, briefing, knowledge, settings/policies, usage |

## Run state machine

States: `queued, triaging, planning, awaiting_approval, executing, verifying, reviewing,
completed, failed, cancelled, interrupted`.

```
queued → triaging | cancelled
triaging → planning | failed | cancelled
planning → awaiting_approval | executing | completed† | failed | cancelled
awaiting_approval → executing | queued‡ | cancelled | failed | interrupted
executing → verifying | awaiting_approval | failed | cancelled | interrupted
verifying → reviewing | failed
reviewing → completed | failed
interrupted → queued (resume) | cancelled
any non-terminal → interrupted (process restart)
```

† plan-only runs (e.g. recommend-autonomy skills) may complete after planning.
‡ approval resolution re-queues the run; the worker resumes from `run.checkpoint`.

Terminal: `completed, failed, cancelled`. Invalid transitions raise `InvalidTransition`
and are unit-tested. Transitions are recorded as `run.*`/`agent.status_changed` events.

## Event model

All provider/tool activity is normalized to (BUILD_BRIEF list, stable):
`run.queued, run.started, agent.status_changed, assistant.message_delta, plan.created,
tool.proposed, approval.required, approval.resolved, tool.started, tool.progress,
tool.completed, tool.failed, artifact.created, verification.completed, run.completed,
run.failed, run.cancelled` (+ `memory.proposed`).

Persistence-first: append to `run_events` (monotonic `seq` per run), then publish to the
in-process bus. SSE (`/api/v1/events/stream`) replays from `since`/`Last-Event-ID` before
attaching live — the DB is the source of truth, live push is an optimization (ADR-012).
Every event has `human_text` for the UI timeline; raw payloads sit behind "Technical details".

## Policy & approval gateway

Tool manifests declare: id/version, connector, capability, input/output JSON Schema,
read/write/destructive class, sensitivity, scopes, side effects, dry-run support, idempotency,
timeout, retry policy, approval policy, undo strategy.

Risk ladder: **R0** local read · **R1** external read · **R2** draft/local reversible write ·
**R3** external reversible write · **R4** destructive/financial/legal/health/identity/broadcast.

`evaluate(tool, connector_state, skill_grant, run_ctx) → allow | require_approval | deny(reason)`:

1. kill switch → deny; connector/domain disabled → deny; tool not in skill allowlist → deny
2. Safe Mode → deny R3/R4 (external writes) outright
3. run mode `read_only` caps at R1; `draft` caps at R2 (R3 downgraded to preview artifact)
4. autonomy: observe→R1, recommend→R1, draft→R2, act_with_approval→R3 via approval,
   act_allowlist→R3 auto only on an explicit policy rule match
5. R4 → deny unless a policy explicitly enables double-confirm (typed phrase) → approval
6. per-tool allow/deny policy rules override upward (deny) but never downward past 1–3

Approvals persist (`approvals` table) with plain-language what/why/target/data/preview/risk/
reversibility/cost and expire after `approval_ttl` (stale approvals cannot execute). Execution
records `tool_calls` with idempotency keys; a resumed run never silently re-fires a completed
external write.

## Agent runtime abstraction

`AgentRuntime` protocol: `start_session, resume_session, send_input, interrupt, stream_events,
approve, deny, cancel, get_usage, close_session`. Adapters:

- **ClaudeAgentRuntime** — official `claude-agent-sdk` (`ClaudeSDKClient`); maps SDK messages to
  normalized events; `can_use_tool` callback bridges permission requests to the approval
  gateway; cwd pinned to configured roots; provider session id persisted in `provider_sessions`.
- **MockAgentRuntime** — deterministic scripted streams for demo mode and tests (including a
  scripted tool proposal that exercises the approval path).
- **OpenAI / Ollama / LangGraph** — registered stubs (`available=False`) proving the interface.

## Data model

Tables (all with `workspace_id`, ids are UUID strings, timestamps UTC):
`workspaces, user_profiles, domains, projects, people, commitments, agent_profiles,
provider_sessions, skills, skill_versions, connectors, connector_tools, policies, schedules,
runs, run_events, tool_calls, approvals, artifacts, memories, memory_sources, context_packs`.
Plus FTS5 virtual table `knowledge_fts` (search index only — files remain canonical).

Memory rows carry source reference, created/last-verified timestamps, confidence, sensitivity,
domain, optional TTL, and a user-visible rationale; they enter via a review queue
(`status=proposed`) and are never auto-committed.

## Failure & recovery

Explicit handling for provider unavailable, auth failure, connector unavailable, schema
mismatch, timeout, rate limit, user denial, partial completion, restart mid-run, stale
approval, duplicate action, verification failure. On startup the worker marks stale claimed
runs `interrupted` (events preserved) and the UI offers resume/restart; resumes replay from
checkpoints and idempotency keys prevent duplicate external writes.

## Observability & budgets

Per run: provider/model, duration, steps, tool calls, tokens + cost estimate when available,
retries, approval wait time, artifacts, verification status. Daily and per-run budgets are
enforced in the worker (budget exceeded → clean failure with reason). Logging is structured
JSON with a redaction filter; an OpenTelemetry adapter is an optional extra, never required.

## Extension points preserved (not built)

`RetrievalProvider` (FTS5 now; Qdrant/LightRAG later), provider routing, Google/Notion/GitHub
production connectors behind the same connector contract, voice providers, Tauri wrapper
(SecretStore → OS keychain), team/Postgres deployment via `workspace_id`.
