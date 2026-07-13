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

## ADR-013 — Adversarial-review fixes; live chat cannot run approval-gated tools **[tightening]**

- **Context:** An external adversarial review (`docs/reviews/ADVERSARIAL_REVIEW_PROMPT.md`)
  produced six confirmed findings (`docs/reviews/codex-findings.md`). All were verified against
  the code and fixed.
- **Decisions:**
  - **F1 (double external write on crash):** the gateway now durably commits a tool call's
    `running` intent *before* dispatching a non-idempotent external write; on resume a
    `running` row for such a tool is treated as ambiguous and is **never auto-replayed** — it
    fails with a reconciliation message. Idempotent/local writes still replay safely.
  - **F2 (symlink write escape):** `local_files`/`obsidian` writes now go through
    `contain_write_target`, which rejects a symlinked final component and requires the
    `realpath`-resolved target to stay within a configured root.
  - **F3 (claim CAS):** run claiming keys off `worker_claim IS NULL` (not `status`), so a
    claimed-but-not-yet-started run can neither be re-selected nor re-claimed; `worker_claim`
    is cleared on re-queue and for stray queued rows at startup.
  - **F4 (worker starvation):** a live chat turn no longer blocks a worker slot waiting on a
    human. If a chat-requested tool needs approval it is **denied** with guidance to run it as
    a skill. Chat is only granted auto-allowed read-only tools today, so this removes a latent
    local DoS without removing any working capability. Promoting chat to approval-gated tools
    requires session parking (persist the provider continuation, release the slot, resume on
    resolution) — deferred.
  - **F5 (SSE dup/omission):** the event stream tracks a delivered high-water mark, pages the
    full backfill, and drops live events at or below the mark.
  - **F6 (event-bus leak):** empty per-run subscription sets are removed on unsubscribe and the
    per-run seq lock is dropped when a run emits a terminal event.
- **Consequences:** The headline "no duplicate external actions" promise now holds across a
  mid-write crash; the filesystem boundary holds against symlink escape; the worker cannot be
  starved or spun into duplicate execution. Regression tests cover each finding.

## ADR-014 — Dry-run as a distinct capability; runtime-registered tools are untrusted **[hardening]**

- **Context:** The review's design concerns: (a) a dry-run was a boolean on the same executor,
  so a buggy/hostile connector could ignore it and perform the real effect during a "preview";
  (b) the policy trusted manifest fields (`external_side_effects`, `read_only`) from
  *runtime-registered* connectors (n8n webhooks, discovered MCP tools) to be truthful, so a
  webhook registered "read only" could auto-run with no approval.
- **Decisions:**
  - **Dry-run is a separate `BaseConnector.preview()` method** that defaults to raising
    `PreviewNotSupported`. The gateway routes a dry-run to `preview()`, never to
    `execute(dry_run=True)`. A connector that hasn't deliberately implemented a preview
    therefore **fails closed** on a dry-run instead of executing. `execute()` asserts
    `not ctx.dry_run`. The registry warns at load if a tool declares `supports_dry_run`
    without a `preview()` override.
  - **Runtime-registered tools are `trusted=False`.** n8n webhooks and discovered MCP tools
    are always classified `external_side_effects=True`, `approval="required"`, `trusted=False`
    — the user's `read_only` hint only lowers the *risk label*, never grants auto-execution.
    The built-in in-process demo MCP server is trusted. Policy gate: an untrusted tool with
    external side effects is **never auto-run**, not even for reads — it needs approval, or an
    explicit `allow` rule created in the policy editor (the one privileged path). Safe Mode
    denies untrusted external calls outright. A `connector_tools.trusted` column (migration
    `0002`) persists this and the Integrations UI shows an "approval" badge.
- **Consequences:** Registering a connector is no longer an implicit grant of trust; a
  mislabeled dry-run can't perform a real effect. Genuinely-safe registered tools cost one
  approval, or a deliberate allow-rule. Alembic `env.py` now ignores FTS5 shadow tables so
  autogenerate stops trying to drop the search index.

## ADR-015 — Round-2 adversarial-review fixes: close the seams around ADR-013/014 **[tightening]**

- **Context:** A second review (`docs/reviews/ADVERSARIAL_REVIEW_PROMPT_R2.md`), briefed to
  attack the round-1 and ADR-014 fixes rather than re-scan the tree, produced twelve confirmed
  findings (`docs/reviews/codex-findings-r2.md`). Each was re-verified against the on-branch code
  (not only the reviewer's isolated repro) and fixed, with a regression test per finding in
  `tests/test_review_r2_fixes.py`.
- **Decisions:**
  - **F1 — Safe Mode beats allow rules.** In the untrusted-external-read branch of `policy.py`,
    Safe Mode is now evaluated *before* the allow-rule loop, so a user `allow` rule can never
    re-enable a registered connector's external call while Safe Mode is engaged.
  - **F2 — a preview never touches the network.** `n8n.preview()` returns a local
    `"Would POST …"` description of the request instead of POSTing a `dry_run:true` body a hostile
    workflow could ignore. Previews are side-effect-free by construction, not by trust.
  - **F3 — hardlinks join symlinks as a write-escape.** `local_files._write` opens with
    `O_NOFOLLOW | O_CLOEXEC` and refuses any target with `st_nlink > 1` *before* truncating.
  - **F4 — discovery cannot traverse out of the roots.** `safe_glob_pattern()` rejects
    `..`/absolute globs; realpath-based `is_within_roots()` re-checks every path from
    `glob`/`rglob`; list/search/knowledge-reindex/obsidian-iter all skip symlinks and
    out-of-root entries.
  - **F5 — secrets stay out of the audit trail on two more paths.** Preview-error text is
    `redact_text`-wrapped before landing in `approval.diff_preview`; edited approval input is
    `redact`-ed like the original input.
  - **F6 — idempotency keys cover the payload.** The n8n key is
    `sha256(run_id | tool_id | canonical_input)`, so two distinct calls to one webhook in one run
    no longer collide into a silent cached no-op.
  - **F7 — an Obsidian write stays in the vault.** `_delegate_write` rejects absolute/`..` paths
    and delegates with the vault as the only root.
  - **F8 — execution uses the run's own workspace config.** The gateway threads the DB
    `Connector.config` through `ExecutionContext.config`; n8n/mcp prefer `ctx.config` over the
    global singleton, so a payload can't route to another workspace's endpoint. Dormant in the
    single-user MVP; manifest *resolution* still reads the singleton (bounded because these tools
    always require approval — documented in the findings report).
  - **F9 — no ghost events on a chat denial.** A read-only `gateway.preflight()` decides
    allow/deny with no ToolCall/Approval/event writes; `_chat_permission` denies non-allowed tools
    with zero persisted or published state, so there is nothing to roll back.
  - **F10 — result persistence is idempotent.** `Memory` gains `run_id`; `_persist_result`
    replaces this run's artifacts and still-*proposed* memories on replay rather than duplicating
    them (approved memories untouched).
  - **F11 — claim ownership is re-checked after the semaphore.** A pure `claim_still_owned()`
    predicate skips a run whose claim was reassigned while the task waited (multi-process defense
    in depth).
  - **F12 — per-run event seq is unique at the DB.** A `UNIQUE(run_id, seq)` constraint plus a
    `SAVEPOINT`-and-retry in `emit()` make a duplicate sequence number impossible even under the
    lock-eviction race the terminal-event lock drop could create.
- **Schema:** migration `0003_memory_run_id_event_seq_unique` adds `memories.run_id` and the
  `run_events` unique index. Idempotent like `0002` (guarded `_has_column`/`_has_unique` + raw
  DDL), so it is a no-op on a fresh `create_all` database (ADR-005) and only patches older ones.
- **Consequences:** Safe Mode is a true hard gate; previews and dry-runs are provably
  side-effect-free; the filesystem boundary holds against symlink *and* hardlink *and*
  glob/symlink-discovery escape; secrets stay redacted on every persistence path; and event/result
  persistence is idempotent across crash-resume. Two items (F8 manifest resolution, F11
  multi-process) are dormant in the single-user/single-process MVP and fixed proportionately, with
  the residual bound written down rather than hidden.

## ADR-016 — Web Research connector; Research Run becomes source-backed **[capability]**

- **Context:** Research Run was knowledge-only and said so — a documented limitation. The roadmap's
  "Near" bucket calls for a Firecrawl-backed Research Run. Adding live web access means a new
  outbound-network surface, which must not violate the connector/gateway boundary or open an SSRF
  hole.
- **Decisions:**
  - **A shipped `web` connector, not direct calls from the skill.** Per architecture invariant 2,
    the skill reaches the web only through typed tools (`web.search`, `web.fetch`) on a manifested
    connector, governed by the gateway. Both are R1 reads, `external_side_effects=false`,
    `trusted=true` — they auto-run within a run and are not blocked by Safe Mode (a read that sends
    a query out is not an external *change*). A policy `confirm` rule can gate them if desired.
  - **Search has a provider + an honest offline fallback.** Firecrawl when `FIRECRAWL_API_KEY` is
    set (referenced by env name via SecretStore, never stored); otherwise a `demo:true` placeholder,
    mirroring MockAgentRuntime so the feature runs credential-less. Fetch is always the keyless
    direct path.
  - **`web.fetch` is SSRF-guarded.** Only `http(s)`; the host must resolve entirely to public
    addresses (loopback/private/link-local/reserved/metadata/multicast/unspecified refused);
    redirects are followed manually with **per-hop** re-validation; non-text/oversized responses are
    rejected. Retrieved content is untrusted **data** — the skill instructs the model to ignore
    instructions embedded in fetched pages (retrieval-injection defense).
  - **Research Run degrades along a clear ladder:** live sources + provider → cited LLM memo
    (`source_backed`); live sources, no provider → deterministic extractive digest (still
    `source_backed`); no live sources + provider → knowledge-based memo (labeled); neither → clean
    failure with setup guidance. The skill manifest now declares `required_connectors: [web]` and
    `allowed_tools: [web.search, web.fetch]` (tightening — it can call nothing else).
- **Consequences:** Research Run produces genuinely source-backed, cited memos when a key is
  configured, and still runs offline. No new third-party SDK enters `apps/web`; the outbound surface
  is one governed connector with an SSRF boundary. Residual (documented in THREAT_MODEL /
  connector README): DNS rebinding between the guard's resolution and httpx's connect is not closed
  in the MVP (would require pinning the connection to the validated IP). *(Closed in ADR-017 F1.)*

## ADR-017 — Round-3 adversarial-review fixes: close the web-egress path and the F2/F6/F10 regressions **[tightening]**

- **Context:** A third review (`docs/reviews/ADVERSARIAL_REVIEW_PROMPT_R3.md`) — the first the
  reviewer could actually build and run — produced thirteen confirmed findings
  (`docs/reviews/codex-findings-r3.md`): five Critical. Two were escalations of documented
  residuals (DNS rebinding, the F8 singleton bound), and two were regressions my own round-2 fixes
  introduced (the event-retry crash, executing a redacted edited value). Each was re-verified
  against the on-branch code and fixed, with a regression test per finding
  (`tests/test_review_r3_fixes.py`, plus updated R2 cases for F10/F13).
- **Decisions:**
  - **F1 — `web.fetch` pins the connection to the validated IP.** The guard resolves the host,
    validates every address, then the request goes to `https://<ip>/…` with the original host as
    the `Host` header and TLS SNI (via httpcore's `sni_hostname` extension). httpx connects to that
    exact IP with no second DNS lookup, and the cert is still verified against the hostname — so a
    DNS-rebinding flip after validation cannot reach a new internal address. Verified: httpcore
    connects TCP to the URL host and uses `sni_hostname` for cert verification; a live pinned HTTPS
    fetch succeeds.
  - **F2 — per-workspace manifest resolution.** The gateway now identifies the owning connector
    config-independently (`owns_tool`), then resolves the tool's `ToolManifest` from THIS
    workspace's `Connector.config` (`_resolve_tool`) and carries that one object through the
    replay/durability check, policy, and execution. A dynamic (n8n/MCP) tool can no longer be
    policy-checked against another workspace's global-singleton manifest while executing its own —
    which had let a write ride in as a "trusted read" past Safe Mode and defeat the no-double-fire
    guard. `_run_connector` treats a present `Connector` row's config as authoritative (no singleton
    fallback).
  - **F3 — writes descend with O_NOFOLLOW on every component.** `open_contained_write` walks from a
    root dir fd, opening each path component with `O_NOFOLLOW | O_DIRECTORY` via `dir_fd`, so a
    parent directory swapped to a symlink after validation (a TOCTOU race) is rejected at open time,
    not just the final component. `st_nlink > 1` still blocks hardlinks.
  - **F4 — the web connector's secret env var is fixed in code** (`FIRECRAWL_API_KEY`); connector
    config can no longer supply an `api_key_env`, so a config edit can't exfiltrate `ANTHROPIC_API_KEY`
    (or any other process secret) to Firecrawl.
  - **F5 — URL credentials are refused and redacted.** `web.fetch` rejects a URL with userinfo, and
    the redactor masks `scheme://user:pass@` in any persisted string, so a basic-auth password never
    lands in `tool_calls`/events/logs.
  - **F6 — the event-seq retry no longer crashes.** The savepoint rollback already detaches the
    conflicting candidate; `emit()` stopped calling `session.expunge()` on it (which raised
    `InvalidRequestError`) and just rebuilds a fresh candidate on retry. Verified with two concurrent
    sessions racing the same run.
  - **F7 — events publish only after commit.** `emit()` queues the fan-out on `session.info`; an
    `after_commit` hook drains it to subscribers and an `after_rollback` hook drops it — a
    transactional outbox, so a rolled-back event never reaches SSE (the general form of R2-F9).
  - **F8 — result persistence keys memories by (kind, content).** A proposal already persisted in
    ANY status is left as-is on replay, so a memory approved between crash and resume is not
    re-proposed as a duplicate.
  - **F9 — citations are validated deterministically.** The memo's `[n]` references are checked
    against the fetched-source count; out-of-range citations (an injected `[999]`) are flagged in
    `unresolved` + a visible warning, not laundered into "Facts".
  - **F10 — the approval edit executes the RAW value.** Storing a redacted copy meant the run wrote
    the literal mask to disk and reported success; edited input is now stored verbatim, and
    credential-shaped edits are rejected instead (still honoring R2-F5).
  - **F11 — migration 0003 reconciles legacy duplicates.** Before creating the unique index it
    renumbers any duplicate `(run_id, seq)` rows gap-free, so a legacy DB that hit the pre-fix event
    race upgrades instead of failing at `CREATE UNIQUE INDEX`. Verified on a hand-built 0002 DB.
  - **F12 — bounded fetch.** The body is streamed with a hard byte counter (no whole-body buffering),
    and HTML→text uses a linear `str.find` scanner instead of the `.*?</\1>` regex that was O(n²) on
    unclosed tags (a ReDoS).
  - **F13 — exact claim ownership.** `claim_still_owned` now requires `worker_claim == worker_id`
    exactly (a cleared or foreign claim aborts), closing the multi-process double-run the looser
    check allowed.
- **Consequences:** The new outbound-network surface is hardened against rebinding SSRF, credential
  leakage, and fetch DoS; the per-workspace boundary is real for policy AND execution; and the two
  regressions from round 2 are closed with tests that exercise the actual race/replay, not just the
  happy path. Remaining honest bound (THREAT_MODEL): true multi-process worker safety still needs a
  leased-claim protocol; the MVP ships single-process.

## ADR-018 — OpenAI + Ollama runtimes, editable integrations, file-backed secrets **[capability]**

- **Context:** The MVP shipped only the Claude and mock runtimes; OpenAI/Ollama/LangGraph were
  honest stubs. Users also needed to add/edit integrations and store API keys from the UI without
  those secrets ever touching the database. (OpenAI OAuth was requested but OpenAI's public API is
  API-key only, so we ship key auth.)
- **Decision:**
  - **Two real runtimes behind the existing `AgentRuntime` contract.** `OpenAIAgentRuntime`
    (Chat Completions, streamed, usage+cost captured) and `OllamaAgentRuntime` (local `/api/chat`,
    streamed, free) share an `HTTPChatRuntime` base that keeps a per-session transcript in memory
    (these APIs are stateless — no server session to resume; a restart honestly starts fresh rather
    than pretending to remember). Both are removed from `STUB_PROVIDERS`; only `langgraph` remains a
    stub. `get_runtime` is now a small factory map, still one singleton per provider so
    interrupt/cancel reach the live instance.
  - **Text-only reasoning engines in the MVP.** Neither new runtime exposes tools to the model, so a
    model turn can produce words but never an external effect — tool use stays with skills/connectors
    behind the policy gateway (consistent with ADR-011/013). The `can_use_tool` bridge is accepted
    for interface parity and unused.
  - **`LocalSecretStore` — file-backed, env wins.** Secrets are read env-first, then from a
    gitignored `data/local/secrets.env` written atomically at mode 0600. Values never enter SQLite,
    logs, or run events (invariant preserved); the secrets API is write-only + list-names + delete
    and never returns a value. A shell-exported value shadows the file and cannot be deleted through
    the API (you unset it in the shell). Cost is a best-effort estimate from a per-model price table;
    provider token counts remain authoritative.
  - **Providers/models + secrets APIs; editable integrations.** `GET /providers` reports
    availability, secret status, and model lists (Ollama models are discovered live via `/api/tags`;
    OpenAI offers a curated list plus live enumeration when a key is present). `model` is stored in
    workspace settings (JSON column — no migration) and flows to the runtime via `SessionContext`.
    Connector resources gained a `DELETE /connectors/{slug}/resources/{name}` so registered n8n
    webhooks / MCP servers can be removed, complementing the existing enable/disable + config edit.
  - **Onboarding re-titles the workspace** on re-onboard (fixes the stale "Alex's Cockpit" name).
- **Consequences:** The cockpit is genuinely provider-independent and self-serviceable: pick a
  provider and model, paste a key that stays on disk at 0600, wire and unwire connectors — all from
  the UI, with the policy gateway still the only thing that authorizes real actions. Verified end to
  end (secret written 0600 and absent from the DB; provider flips available once keyed; webhook
  add→remove; model persists) plus 24 new unit/integration tests (`respx`-mocked OpenAI/Ollama
  streams, secret-store round-trip, providers/secrets/resource APIs). Honest bound: without a
  provider key or a local Ollama, those providers report `needs setup` and the cockpit stays on the
  offline demo runtime.

## ADR-019 — OttoOS visual redesign: presentation-layer evolution, nothing removed **[capability]**

- **Context:** A Claude Design handoff (`OttoOS Design Spec` + interactive `OttoOS Cockpit`
  prototype, direction 1a "Flight Deck", champagne gold) rebrands the cockpit as **OttoOS** and
  restructures the shell around judgment. The spec's own constraint: backend, contracts, and policy
  gateway unchanged; steps 1–5 of its "Push to code" plan require no backend changes.
- **Decision:**
  - **Tokens, not forks.** `globals.css` swaps values under the SAME custom-property architecture,
    adding the hairline ladder (shell→card→row→control→button), the five-step ivory ink ladder, the
    champagne-gold accent family (`#c9a961`, on-accent `#171308`), judgment amber (reserved
    exclusively for "needs you"), desaturated `--ok`, and well/tile/nav surfaces. Dark "midnight
    graphite" becomes the DEFAULT; light "parchment" is preserved with a gold-shifted accent.
  - **Three fonts, three registers** via `next/font/google` (self-hosted at build): Instrument Sans
    for all UI, Newsreader italic for Otto's voice only (`.otto-voice`), IBM Plex Mono for technical
    truth (paths, IDs, risk chips, `.section-label`). Radii 16/12/9.
  - **Shell = four zones with one job each.** Nav grouped OPERATE/CONTEXT/SYSTEM with executive
    labels over UNCHANGED routes (Home→Briefing, Projects→Missions, Skills→Agents,
    Approvals→Decisions, People→Relationships, Integrations→Systems, History→Archive,
    Agenda→Calendar); a persistent **command band** (Otto orb + live status line + composer with
    autonomy segments mapping 1:1 to run modes + budget/systems vitals) that hands off to `/command`
    via URL params; a **trust strip** closing every screen; the ambient rail (inline approve on mini
    decision cards, live timeline, systems dots, counts footer). **Work modes** (Command/Focus/Deep)
    collapse zones around attention — pure client state, ESC exits, approvals queue silently.
  - **The Otto pulse stays real state, never decoration** — same `deriveOttoState` semantics, new
    champagne-sphere rendering, status-line pairing, `aria-live` announcements, reduced-motion
    degrades to color + label.
  - **Decision card anatomy preserved field-for-field** (what/why/target/reversibility/diff/
    technical details/note/Approve once/Deny/Cancel the run) with Modify as a relabel of the
    existing edit hook, diff wells coloring +/− lines, amber card surface as the only amber-tinted
    surface, and a/d keyboard shortcuts on the focused card.
  - **Nothing fabricated.** Spec slots that need new backend fields (mission progress/milestone/
    confidence, briefing synthesis grid, approvals Defer, people next-touch service) are OMITTED or
    derived client-side from real fetched data only; they remain the spec's step-6 follow-up. The
    prototype's stale "OpenAI/Ollama PLANNED" strip is superseded by the live provider/model/secrets
    surfaces from ADR-018, restyled not removed.
- **Consequences:** Every route, control, testid, and honesty line survives restyled; e2e specs
  updated only where visible labels changed (palette search term, Decisions heading, mobile tab).
  The redesign is reversible by reverting presentation files — no schema, API, or policy change
  rides along.
