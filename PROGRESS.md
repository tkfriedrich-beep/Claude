# PROGRESS.md — build log

Status legend: ✅ done · 🟡 in progress · ⬜ not started · ❌ blocked

## Current state

**MVP complete and verified (2026-07-12).** All milestones done; acceptance criteria below.

| Milestone | Status |
| --- | --- |
| M0 — Foundation & design contract | ✅ |
| M1 — Durable local core | ✅ |
| M2 — Claude runtime & live command control | ✅ (incl. live Claude session verified) |
| M3 — Useful local skills | ✅ |
| M4 — Integrations & automations | ✅ |
| M5 — Hardening & polish | ✅ |

## Final test results (all actually executed 2026-07-12)

| Gate | Result |
| --- | --- |
| `pytest` (control plane) | **87 passed** at MVP; **155 passed** after review rounds 1–3 + Web Research (see below) |
| `ruff check` + `ruff format --check` | clean |
| `mypy src` | no issues in 52 files |
| `pnpm typecheck` (web) | clean |
| `pnpm lint` (web) | clean |
| `vitest` | 6 passed |
| `pnpm build` (web) | clean production build |
| Playwright e2e (desktop + mobile, real control plane) | **10 passed** (see list below) |
| `python -m cockpit.doctor` (fresh env) | 0 failures, 1 warning (no workspace yet — expected) |
| Live Claude runtime | chat turn completed (69 tokens out, $0.17 captured), resume in same provider session verified |

E2E coverage: onboarding+demo → cockpit · keyboard palette + axe (serious/critical = 0) ·
project-pulse to completion with sources · **approval flow: deny skips / approve executes
exactly once, file verified on disk, nothing written before approval** · history + replayable
timeline · chat streaming (demo runtime) · mobile bottom-tab navigation, no horizontal
overflow · desktop + mobile screenshots → `docs/screenshots/`.

## MVP acceptance criteria (BUILD_BRIEF) — evidence

1. ✅ Setup & launch documented, no Docker (`make setup/dev`, README, RUNBOOK; exercised)
2. ✅ Demo mode without credentials (mock runtime + demo data; e2e passes with no keys)
3. ✅ Polished responsive home, keyboard accessible, verified desktop+mobile (screenshots)
4. ✅ Otto pulse reflects real run state; `prefers-reduced-motion` disables all animation
5. ✅ Claude-backed session: start/stream/interrupt/cancel/resume (mock in e2e; **real Claude
      verified live** — tokens/cost captured, resume via stored external session id)
6. ✅ Proposed side effect → approval; cannot execute before it (gateway test + e2e fs check)
7. ✅ Safe Mode blocks external writes (policy unit test + gateway test)
8. ✅ Project Pulse reads local vault, source-linked result (pytest + e2e)
9. ✅ Decision Memo → durable Markdown + JSON artifacts (pytest + e2e API check)
10. ✅ Idea Triage never alters sources without approval (pytest + e2e: 0 files before, 1 after)
11. ✅ Run history survives restarts (SQLite; interrupted-run recovery + resume path tested)
12. ✅ Connector health & permissions visible (Integrations UI, health checks, tools dialog)
13. ✅ Secrets absent from logs/events (redaction unit tests; config API rejects secret-like)
14. ✅ Unit tests: policy (20), FSM, schemas, routing, gateway, skills — 87 total
15. ✅ E2E: onboarding/demo, skill run, approval deny, approval success, history, responsive nav
16. ✅ `make doctor` reports prerequisites/config with fixes (CLI + API verified)
17. ✅ `make test` passes (87 + 6); no hidden failures
18. ✅ README: setup, architecture, security model, data locations, backup/export, troubleshooting

## Post-MVP: adversarial review round 1 (2026-07-12)

An external adversarial review (`docs/reviews/codex-findings.md`, prompt in
`docs/reviews/ADVERSARIAL_REVIEW_PROMPT.md`) returned 6 findings. All were **verified against
the code and fixed**; each has a regression test in `tests/test_review_fixes.py` (10 tests).
See DECISIONS ADR-013.

| # | Finding | Sev | Verdict | Fix |
| --- | --- | --- | --- | --- |
| F1 | Crash after external effect, before completion commit → resume re-fires the write | Critical | CONFIRMED | durable `running` intent committed before dispatch; a `running` non-idempotent external call is never auto-replayed on resume |
| F2 | `local_files`/`obsidian` write follows a symlinked final component out of roots | Critical | CONFIRMED | `contain_write_target` rejects symlinked tail + `realpath` must stay within a root |
| F3 | `claim_next_run` not a real CAS (leaves `status=queued`) → duplicate/unbounded task spawn | High | CONFIRMED | claim keys off `worker_claim IS NULL`; cleared on requeue + startup |
| F4 | Two chat approvals hold both worker slots for 600s (latent — not reachable today) | High | CONFIRMED (latent) | live chat denies approval-gated tools instead of blocking; no worker-slot wait |
| F5 | SSE backfill can duplicate events and omit >500 | Medium | CONFIRMED | high-water-mark dedupe + paginated full backfill |
| F6 | EventBus retains a lock + run-key per run forever | Medium | CONFIRMED | evict empty subscription sets; drop seq lock on terminal event |

Test gate after fixes: **pytest 97 passed** (was 87; +10 regression) · ruff + mypy clean ·
vitest 6 · **e2e 10/10** (approval/resume path re-verified under the new claim + intent logic).

Note the reviewer worked static-only (no network to clone/run), so its stated mechanism for F1
(row "still running") was refined on verification — the intent row is actually rolled back on
crash, which is why the durable pre-dispatch commit is the fix. F4 was confirmed real but not
reachable in the shipped system (no chat-exposed approval-gated tool); fixed proactively.

## Post-MVP: hardening round 2 — design concerns (2026-07-12)

Acted on the two design concerns from the review (DECISIONS ADR-014):

- **Dry-run is now a distinct capability.** `BaseConnector.preview()` defaults to raising
  `PreviewNotSupported`; the gateway routes previews to `preview()`, never `execute(dry_run)`.
  A connector without a real preview fails closed instead of performing the effect. Registry
  warns at load if `supports_dry_run` is declared without a `preview()`.
- **Runtime-registered tools are untrusted.** n8n/MCP tools → `trusted=False`, always
  external + approval-required; a `read_only` hint only lowers the risk label, never grants
  auto-run. Policy never auto-runs an untrusted external tool (even reads); Safe Mode denies
  them; loosening is only via an explicit allow rule. New `connector_tools.trusted` column
  (migration `0002`, idempotent per ADR-005); Integrations UI shows an "approval" badge and a
  registration notice. Alembic `env.py` now ignores FTS5 shadow tables.

Test gate: **pytest 106 passed** (+9 in `tests/test_hardening.py`) · ruff + mypy clean ·
tsc + eslint clean · **e2e 10/10** · migration `0002` verified up/down/up.

## Post-MVP: adversarial review round 2 (2026-07-12)

A second review (`docs/reviews/codex-findings-r2.md`, prompt in
`docs/reviews/ADVERSARIAL_REVIEW_PROMPT_R2.md`), briefed to attack the round-1 and ADR-014
fixes, returned **12 findings** (1 Critical-class, 5 High, 4 Medium, 2 Low). Each was
**re-verified against the on-branch code** (not only the reviewer's isolated repro — the
reviewer again had no network to clone/run) and **fixed**, with a regression test per finding in
`tests/test_review_r2_fixes.py` (15 tests). See DECISIONS ADR-015 for the full list. Highlights:

- **F1** Safe Mode now beats an `allow` rule for untrusted external reads (was: allow-rule
  override). **F2** `n8n.preview()` makes no HTTP call (was: real POST during a "dry run").
- **F3** writes reject hardlinks (`O_NOFOLLOW` + `st_nlink>1`); **F4** list/search/reindex reject
  `..`/absolute globs and skip symlinked/out-of-root entries; **F7** Obsidian writes stay in the
  vault. **F5** secrets redacted on the approval-edit and preview-error paths. **F6** n8n
  idempotency key covers the payload.
- **F8** connector config is threaded per-workspace through `ExecutionContext` (no cross-workspace
  endpoint routing). **F9** denied chat tools use a read-only preflight — no ghost SSE events.
  **F10** result persistence replaces (not duplicates) on resume. **F11** `run_one` re-verifies
  claim ownership. **F12** `UNIQUE(run_id, seq)` + savepoint-retry in `emit()`.

Schema delta: migration `0003_memory_run_id_event_seq_unique` (`memories.run_id` +
`run_events` unique index), idempotent per ADR-005, verified up/down/up on a fresh DB.

Test gate (all actually executed 2026-07-12): **pytest 121 passed** (+15 in
`tests/test_review_r2_fixes.py`) · `ruff check` + `ruff format --check` clean · `mypy src` no
issues in 52 files · `pnpm typecheck` + `pnpm lint` clean · `vitest` 6 passed · migration `0003`
verified up→base→up. Playwright e2e not re-run this round: the changes are control-plane-internal
with no API-contract or event-shape change, and the full worker/skill/chat pipeline is covered by
the 121 backend tests (M5's 10/10 e2e remains the last browser result).

## Post-MVP: Web Research connector + source-backed Research Run (2026-07-12)

Turned the previously knowledge-only Research Run into a live, source-backed skill (DECISIONS
ADR-016). New shipped `web` connector with two R1 read tools reached only through the Tool
Gateway (invariant 2):

- **`web.search`** — Firecrawl-backed when `FIRECRAWL_API_KEY` is set (secret referenced by env
  name via SecretStore, never stored), with a clearly `demo`-labeled offline fallback so the
  skill runs credential-less.
- **`web.fetch`** — keyless direct fetch with an **SSRF guard** (only http(s); host must resolve
  entirely to public IPs; loopback/private/link-local/**metadata `169.254.169.254`**/reserved
  refused; redirects followed manually with per-hop re-validation; non-text/oversized rejected).
  Retrieved content is untrusted **data** — the skill tells the model to ignore instructions
  embedded in fetched pages.

Research Run degrades along a clear ladder: live sources + provider → cited LLM memo
(`source_backed`); live sources, no provider → deterministic extractive digest (still
`source_backed`); no live sources + provider → knowledge-based memo (labeled); neither → clean
failure. Manifest now declares `required_connectors: [web]` + `allowed_tools: [web.search,
web.fetch]` (tightening).

Verified live in-container: `web.fetch` against real pages (pypi.org → title + extracted text
through the agent proxy); SSRF guard blocks the metadata IP live; offline search returns
demo-labeled results. (Arbitrary public hosts like example.com are 403'd by the environment's
network policy — the connector surfaces that as a clean error.)

Test gate (all actually executed 2026-07-12): **pytest 140 passed** (+19 in
`tests/test_web_research.py`: SSRF guard matrix, direct fetch/extraction, redirect re-validation,
binary rejection, offline + Firecrawl-mocked search, and full-pipeline source-backed/knowledge
Research Run) · `ruff check` + `ruff format --check` clean · `mypy src` no issues in 53 files.
Residual: DNS rebinding (THREAT_MODEL / connectors/web/README.md).

## Post-MVP: adversarial review round 3 (2026-07-12)

The third review (`docs/reviews/codex-findings-r3.md`) was the first the reviewer could **build and
run** (it reported the baseline `140 passed`). It returned **13 findings** — 5 Critical — against
the round-2 fixes and the new web-egress path. Each was re-verified against the on-branch code and
fixed, with a regression test per finding (`tests/test_review_r3_fixes.py`, plus updated R2 cases
for F10/F13). See DECISIONS ADR-017. Highlights, honestly including two regressions from round 2:

- **F1** `web.fetch` now **pins the connection to the validated IP** (Host + SNI preserved), closing
  the DNS-rebinding SSRF that was a documented residual. Verified: httpcore connects to the pinned
  IP and still verifies the cert against the hostname; a live pinned HTTPS fetch works.
- **F2** per-workspace manifest resolution — policy/durability/execution all use the workspace's own
  `Connector.config`, closing a Safe Mode bypass + double-fire for a dynamic n8n/MCP tool.
- **F3** writes descend with `O_NOFOLLOW` per component (parent-symlink TOCTOU). **F4** the web
  secret env var is fixed in code (no config redirect → no `ANTHROPIC_API_KEY` exfil). **F5** URL
  userinfo rejected + redacted.
- **F6** (regression) the event-seq retry no longer crashes on `expunge`; **F7** events publish only
  after commit (transactional outbox). **F8** approved-then-resumed memories aren't duplicated.
  **F9** out-of-range citations are flagged. **F10** (regression) the approval edit executes the raw
  value, not the redacted mask. **F11** migration 0003 reconciles legacy duplicate event seqs
  (verified on a real 0002 DB). **F12** streamed byte cap + linear HTML parser (no ReDoS).
  **F13** exact claim ownership.

Test gate (all actually executed 2026-07-12): **pytest 155 passed** (+15 in
`tests/test_review_r3_fixes.py`) · `ruff check` + `ruff format --check` clean · `mypy src` no issues
in 53 files · `pnpm typecheck` + `pnpm lint` clean · `vitest` 6 passed · migration `0003` verified
up/down/up **and** on a hand-built legacy-duplicate 0002 DB. Live in-container: IP-pinned fetch, SSRF
rebinding rejection, and the parent-symlink write block all confirmed.

## Known limitations (honest)

- Claude chat exposes read-only tools only (ADR-011); writes go through skills + approvals.
- Research Run is source-backed via the `web` connector (ADR-016); live search needs
  `FIRECRAWL_API_KEY`, else it labels the memo knowledge-based. `web.fetch` works keyless.
- Idea scoring is keyword-heuristic — labeled as such in scorecards/SKILL.md.
- MCP stdio path implemented but exercised via the in-proc demo server in tests; real stdio
  servers depend on the user's local commands.
- Local process discipline ≠ hardened sandbox (see THREAT_MODEL).
- The `chat command streams` e2e showed one flake during development (dev-server Fast Refresh
  mid-run); final full runs passed 10/10.

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

### Web cockpit + M5 — Hardening & polish — ✅ (2026-07-12)

- [x] Full cockpit UI (all 9 core screens + agenda/projects/people/knowledge), design tokens,
      Otto pulse, activity rail, ⌘K palette, mobile bottom tabs
- [x] Loading/empty/error/permission states everywhere; demo data labeled; reduced motion
- [x] Playwright e2e vs a REAL control plane (isolated data dir): 10/10 passing incl. axe
      (0 serious/critical) and the full approval deny→approve→exactly-one-write flow
- [x] Desktop + mobile screenshots in docs/screenshots/
- [x] a11y fix from axe (role=status on live indicator); UI polish from screenshot review
- [x] Live Claude runtime verified (chat + resume, usage captured)
- [x] Final gates re-run after every fix (tables above)

### M6 — Providers, editable integrations & secrets — ✅ (2026-07-13)

- [x] `OpenAIAgentRuntime` (Chat Completions, streamed deltas + token usage/cost) and
      `OllamaAgentRuntime` (local `/api/chat`, streamed, free) on the existing `AgentRuntime`
      contract via a shared `HTTPChatRuntime` base; both dropped from the stub list
- [x] `LocalSecretStore` — env-over-file, gitignored `data/local/secrets.env` at mode 0600;
      write-only secrets API (list names / set / delete), values never in DB, logs, or events
- [x] Providers/models API (`GET /providers`): availability, secret status, Ollama live model
      discovery + OpenAI curated/live list; model persisted in workspace settings → runtime
- [x] Editable integrations: enable/disable + config edit (existing) plus resource removal
      (`DELETE /connectors/{slug}/resources/{name}`) for n8n webhooks / MCP servers
- [x] Web: Integrations page gets a provider+model selector, a write-only Secrets manager, and
      per-connector resource management; Settings provider dropdown extended
- [x] Gates: control-plane pytest 171 passed; ruff + mypy clean; web tsc + eslint clean;
      vitest 6 passed; `next build` 16/16 pages; contracts regenerated (`make contracts`)
- [x] Live smoke: secret saved at 0600 and absent from the DB; OpenAI flips to available once
      keyed; n8n webhook add→remove; model persists across settings reads

### M7 — OttoOS visual redesign (presentation layer, ADR-019) — ✅ (2026-07-14)

- [x] Foundations: champagne-gold/graphite token system (hairline + ink ladders, judgment
      amber, ok/diff tones) under the same custom-property names; dark "midnight graphite"
      default, parchment preserved gold-shifted; Instrument Sans / Newsreader italic (Otto's
      voice only) / IBM Plex Mono via next/font; radii 16/12/9
- [x] Shell: nav grouped OPERATE/CONTEXT/SYSTEM with executive labels over unchanged routes;
      persistent command band (Otto hero + live status + composer + autonomy segments +
      budget/systems vitals → hands off to /command); trust strip; Command/Focus/Deep work
      modes (ESC exits); ambient rail (inline approve, live timeline, systems dots, counts);
      expanded ⌘K palette (GO TO/RUN/CONTROL/MODE); canonical decision card (Modify hook,
      diff +/- coloring, a/d keys); champagne-sphere Otto pulse, same state semantics
- [x] All 13 screens restyled: Briefing, Command (band handoff via searchParams), Missions,
      Agents (+detail autonomy ladder), Decisions (live tab tallies), Calendar,
      Relationships (real next-touch derivation), Knowledge, Automations, Systems (provider
      tiles + write-only Secrets + connector monogram cards — ADR-018 features intact),
      Archive (+run detail, "Verification"/"Unresolved" kept), Settings (segmented exec mode,
      MIDNIGHT/PARCHMENT theme, all controls), Onboarding (retoken, flow + testids intact) —
      nothing removed, testids kept, no fabricated data (backend-less spec slots omitted
      per ADR-019)
- [x] Gates: web tsc + eslint clean; vitest 6 passed; `next build` 16/16; unit/e2e specs
      updated for renamed labels; live visual smoke against a real control plane (briefing,
      decisions, systems, settings, archive screenshots verified)
- [ ] Spec step-6 backend follow-ups: approvals defer, mission progress/milestone/confidence,
      briefing synthesis fields, people next_touch service-side
