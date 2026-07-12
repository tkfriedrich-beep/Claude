# PROGRESS.md — build log

Status legend: ✅ done · 🟡 in progress · ⬜ not started · ❌ blocked

## Current state

**Control plane (M1+M2) done and verified; M3 backend skills done.** Web app next.

| Milestone | Status |
| --- | --- |
| M0 — Foundation & design contract | ✅ (docs/scaffold) · cockpit shell lands with the web app |
| M1 — Durable local core | ✅ |
| M2 — Claude runtime & live command control | ✅ (backend; UI pending) |
| M3 — Useful local skills | ✅ (backend + demo data; UI pending) |
| M4 — Integrations & automations | ✅ (backend; UI pending) |
| M5 — Hardening & polish | ⬜ |

## Environment (inspected 2026-07-12)

- Linux 6.18.5 container, repo `tkfriedrich-beep/Claude`, branch
  `claude/build-brief-implementation-dbre2i`
- Node v22.22.2, pnpm 10.33.0, Python 3.12.3, uv 0.8.17, GNU Make 4.3
- `claude` CLI present at `/opt/node22/bin/claude` (Agent SDK can spawn it)
- Playwright Chromium preinstalled at `/opt/pw-browsers` (do not run `playwright install`)
- Pre-existing unrelated repo content preserved: `copy_photos.sh`, `find_largest_files.sh`,
  `iran-news-timeline/`, `.claude/skills/voluntary-mind-essay/`

## Milestone log

### M0 — Foundation & design contract — ✅ (2026-07-12)

- [x] Environment inspection · BUILD_BRIEF.md committed
- [x] README, CLAUDE.md, docs/ ×7, DECISIONS.md (ADR-001..012), PROGRESS.md
- [x] Makefile, pnpm workspace, uv project, .env.example
- Design tokens + cockpit shell were folded into the web-app milestone (same commit series).

### M1 — Durable local core — ✅ (2026-07-12)

- [x] FastAPI app (`/api/v1`: health, doctor, onboarding, commands, sessions, runs, SSE
      events, approvals, skills, connectors, automations, artifacts, memories, briefing,
      agenda, projects, people, knowledge, settings, domains, policies, usage)
- [x] SQLite WAL + Alembic (`0001_initial`, 22 tables + FTS5), UTC-safe datetimes
- [x] Run FSM (`state_machine.py`) — invalid transitions raise, tested
- [x] Persistence-first event store + in-process bus + SSE with Last-Event-ID backfill
- [x] Policy engine (R0–R4 × autonomy 0–5 × Safe Mode/kill switch/draft/shadow) — 20 tests
- [x] Tool Gateway: JSON-Schema validation both ways, approval pause/resume via re-queue,
      idempotent replay (approved external writes never re-fire), retries, timeouts,
      dry-run previews on approval cards
- [x] Skill + connector registries loading `skills/*` and `connectors/*` manifests
- [x] Worker loop (runs table = job queue, CAS claim) + scheduler (Shadow Mode,
      approval-expiry sweep) + restart recovery → `interrupted`
- [x] Structured JSON logging with recursive secret redaction

*Test gate (actual):* `uv run pytest -q` → **87 passed** · `ruff check` clean ·
`ruff format --check` clean · `mypy src` → no issues in 52 files.

**Live verification (uvicorn, demo workspace):** onboarding seeded 2 real runs;
project-pulse completed with source-linked results; business-idea-triage paused at
`awaiting_approval`, approve→resume executed exactly one write-back (file verified on disk),
two denials recorded as skipped; SSE stream delivered `id/event/data` frames with human_text;
chat run on mock runtime streamed deltas and exercised the gateway permission bridge.

### M2 — Claude runtime & live command control — ✅ backend (2026-07-12)

- [x] `AgentRuntime` protocol (start/resume/send_input/stream_events/interrupt/approve/deny/
      cancel/get_usage/close)
- [x] `ClaudeAgentRuntime` on official claude-agent-sdk 0.2.116 (API surface verified by
      introspection: ClaudeSDKClient, ClaudeAgentOptions incl. can_use_tool/resume/
      setting_sources, PermissionResult types, ResultMessage usage fields)
- [x] Read-only builtin tools pinned to configured roots; everything else denied (ADR-011);
      permission callback bridges to the approval gateway
- [x] Provider session ids persisted separately (`provider_sessions.external_session_id`)
- [x] Usage capture (tokens/cost) from ResultMessage; one-shot generation for skill
      enrichment; MockAgentRuntime for demo/tests; OpenAI/Ollama/LangGraph stubs refuse honestly
- [ ] Live end-to-end Claude session — requires ANTHROPIC_API_KEY at runtime; adapter unit
      tests cover permission/containment logic (documented limitation)

### M3 — Useful local skills — ✅ backend (2026-07-12)

- [x] Local Files + Obsidian connectors (bounded roots, diff previews, approval-gated writes)
- [x] Project Pulse, Decision Memo (md+json export, LLM-assisted when provider healthy),
      Business Idea Triage (approval-gated write-backs) — fully implemented + tested
- [x] Morning Brief + Daily Plan (demo-labeled agenda), Weekly Review, Commitment Sweep
      (→ Memory Review queue), Research Run (fails cleanly without provider)
- [x] Demo vault/bizideas/agenda/emails/pages/issues content; demo seeder runs REAL pipeline
      runs (no fabricated history)

### M4 — Integrations & automations — ✅ backend (2026-07-12)

- [x] n8n connector: HMAC-signed webhooks, env-referenced secrets, schema-bound, dry-run aware
- [x] MCP registry: stdio discovery via official `mcp` SDK (optional extra) + in-proc demo
      server; tools normalized to R1/R3 + approval defaults
- [x] Shadow-Mode schedules (draft semantics forced) + run-now + pause; approval TTL sweep
- [x] Google/Notion/GitHub mock connectors (health=mock, `demo:true` payloads, read-only)
- [x] Config API rejects credential-shaped values (secrets stay in env)

### M5 — Hardening & polish — ⬜ (web app + e2e + screenshots next)
