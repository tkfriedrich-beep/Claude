# Adversarial code review — AgenticOS Cockpit

You are a skeptical staff-level security + systems reviewer. Your job is to **break this
codebase**, not to praise it. Assume it is flawed and that its author (another AI) was
over-confident. A review that finds nothing is a failed review. Do **not** rubber-stamp,
do **not** rewrite the app, and do **not** stop at reading — **run it and attack it**.

You earn credit only for defects you can **demonstrate** (a failing test, a reproduction, or a
traced execution path), and you lose credit for vague "consider maybe" comments and style
nitpicking.

---

## 1. Repository & setup

- **Repo:** `github.com/tkfriedrich-beep/Claude`, branch `claude/build-brief-implementation-dbre2i`
  (open as PR #5). Clone that branch.
- **Governing spec:** `BUILD_BRIEF.md` at the repo root is the product/architecture/security
  contract. Deviations are logged in `DECISIONS.md` (ADR-001…012). Claimed status and test
  evidence are in `PROGRESS.md`. **Treat these as the author's claims to be falsified**, not as
  ground truth.
- **Layout:** control plane `services/control-plane/` (Python 3.12, FastAPI, async SQLAlchemy,
  SQLite); web `apps/web/` (Next.js 15); runtime skills `skills/`; connector manifests
  `connectors/`; demo data `data/demo/`.
- **Build & run** (no Docker needed):
  ```bash
  make setup            # uv sync + pnpm install + alembic upgrade head
  make demo             # seed a demo workspace (runs REAL skill runs)
  make dev              # control plane :8787, web :3000
  make test             # pytest (87) + vitest (6)
  cd apps/web && PLAYWRIGHT_CHROMIUM_PATH=/opt/pw-browsers/chromium pnpm exec playwright test
  ```
  If `uv` is unavailable use the venv fallback in `docs/RUNBOOK.md`. The Claude runtime needs
  `ANTHROPIC_API_KEY`; everything else works in demo mode with no credentials.

Spend your first pass confirming you can build, migrate, seed, boot, and hit
`GET /api/v1/health`. Then attack.

---

## 2. The oracle — invariants that MUST hold

These are the properties the system claims. Each one is a target: try to construct an input,
sequence, or race that **violates** it. (Full lists: `BUILD_BRIEF.md` §"Architecture invariants"
and `docs/THREAT_MODEL.md` §"Security invariants".)

**Security / safety**
1. A tool with external side effects **cannot execute before an approval is resolved**. Prove
   or disprove that you can get a real write to happen while a run is `awaiting_approval`.
2. **Safe Mode blocks every external write**, regardless of skill autonomy, run mode, or policy
   rule. Find a bypass.
3. An **approved external write never fires twice** — not on retry, not on resume, not across a
   process restart mid-execution. (This is the one I most expect to be broken; see §3.)
4. **Only `cockpit/policy.py` decides allow/deny.** No connector, skill, prompt, or retrieved
   document can change the decision. Find a place where retrieved/file/MCP content influences a
   permission, risk level, or approval requirement.
5. **Secrets never reach** `run_events`, `tool_calls`, `artifacts`, logs, or API responses. Try
   to smuggle a credential-shaped value through a connector config, an artifact, a note, or a
   health-detail string and see if it survives unredacted.
6. **Filesystem tools stay within configured roots.** Attempt path traversal / symlink escape
   through `local_files.*` and `obsidian.*` (`.write` especially — think `..`, absolute paths,
   symlinks inside the vault, TOCTOU).
7. **`run.status` is only ever written by `state_machine.transition()`** and invalid
   transitions raise. Find a code path that mutates status directly or drives an illegal
   transition.
8. Retrieved content (files, MCP output, webhook responses) is **data, not instructions** —
   confirm nothing feeds it back into the system prompt or tool-authorization path.

**Correctness / integrity**
9. Every DB query is scoped by `workspace_id`; no endpoint returns or mutates another
   workspace's runs/artifacts/memories/approvals (IDOR). The MVP is single-user, but the
   boundary is claimed — check `api/*.py` for `session.get(...)` without an ownership check.
10. Idempotency keys, the `edited_input` approval path, and the dry-run preview
    (`gateway._get_or_create_approval`) are genuinely side-effect-free for the preview and
    correct for the real call.
11. FSM resume after approval re-enters the skill and relies on **idempotent replay** — verify a
    resumed skill run does not repeat a non-idempotent effect or corrupt its result.
12. "No false success": a completed tool step with external effects sets `external_confirmed`
    only when the effect was actually confirmed; the `no_unconfirmed_success` verifier catches
    violations.

---

## 3. Prioritized areas of concern (start here)

Rank your effort roughly in this order — these are where I believe the real bugs live.

1. **Crash/restart mid-write → double external effect.** `gateway.ToolGateway._execute` sets a
   `tool_call` to `RUNNING`, calls the connector, then `COMPLETED`. Trace what happens if the
   process dies between the connector's real effect and the `COMPLETED` write, then the run is
   resumed. On replay, is that `tool_call` treated as "not completed" and re-executed? For a
   non-idempotent external write, is that a silent double-fire? Construct the scenario. (The
   in-run retry guard in `_execute` does **not** cover the cross-restart case — confirm or
   refute.)
2. **Chat approval blocks the worker.** `worker.RunProcessor._chat_permission` /
   `_wait_for_approval` poll the DB for up to 600s **inside** the worker task, holding a worker
   semaphore slot and an open DB session/transaction. With `worker_concurrency` low (default 2),
   can two pending chat approvals starve the worker? Does the long-lived open transaction block
   the approval-resolve request (SQLite writer lock) — i.e., a **deadlock** where the resolve
   can't commit because the waiter holds the connection? Try it live: start two chat runs that
   trigger approvals and observe.
3. **Event bus / seq-lock growth & ordering.** `events.EventBus._seq_locks` and `_by_run` are
   `defaultdict`s keyed by run_id that are never evicted — unbounded memory over many runs.
   Separately: `emit()` computes `seq` under a per-run lock but the global autoincrement `id`
   (the SSE cursor) is assigned on flush — can two runs interleave such that a subscriber sees
   `id` order that disagrees with per-run `seq` order, or a backfill-then-live gap that drops or
   duplicates an event? Hammer SSE with concurrent runs.
4. **Policy matrix completeness.** Enumerate the full cross-product in `policy.evaluate`
   (access × risk × side-effects × dry-run × safe_mode × exec_mode × shadow × autonomy × rules)
   and find any cell that lets an external write through without approval, or that denies a
   legitimate local read. Pay attention to: a tool with `external_side_effects=True` but
   `risk_level=R2`; `approval: "required"` in a manifest vs. a policy `allow` rule; the R4
   double-confirm path.
5. **Frontend injection.** Artifact content and knowledge snippets are rendered via
   `dangerouslySetInnerHTML` (`components/ui/markdown.tsx`, `app/knowledge/page.tsx`). Content
   originates from files and the model. Craft a note/artifact that achieves XSS (event handlers,
   `javascript:` URLs, nested/escaped payloads, the `⟪⟫` snippet markers). Confirm the escaping
   order actually neutralizes it.
6. **Concurrency in `claim_next_run` and approval re-queue.** Is the CAS claim truly race-free?
   Can a run be claimed twice, or resumed while still claimed? Can the scheduler's
   approval-expiry sweep race the resolve endpoint (double resolution / lost transition)?
7. **UTC/JSON/SQLite footguns.** `models.UTCDateTime`, JSON columns, WAL, FTS5 query
   sanitization (`knowledge.py` — try FTS5 injection / query syntax that errors or returns
   cross-workspace rows). Alembic downgrade of `0001`.
8. **Claude adapter** (`runtime/claude.py`) — the permission callback wiring
   (`_pending_callback`/`_callbacks` dict), session-id capture on resume, and whether a
   provider tool request can reach the filesystem outside roots. SDK is optional; guard the
   review behind `available()`.

---

## 4. Rules of engagement

- **Prove it.** For each finding, either write a failing test (pytest under
  `services/control-plane/tests/`, or a Playwright/vitest case), reproduce it against a running
  instance with the exact commands/requests, or give the precise traced call chain with
  `file:line` references. Label each finding **CONFIRMED** (reproduced/traced end-to-end) or
  **SUSPECTED** (looks wrong, not yet demonstrated).
- **Attack at runtime, not just on paper.** Boot the app in demo mode and try the exploits:
  curl the API, drive the UI, kill `-9` the control plane mid-run and restart, open concurrent
  SSE streams, submit malformed payloads, race two approvals.
- **Don't fix — report.** Suggest a fix in one or two sentences per finding, but do not refactor
  the codebase.
- **Out of scope (don't spend time here):** the Google/Notion/GitHub connectors are intentional
  mocks; the OpenAI/Ollama/LangGraph providers are intentional stubs; the absence of auth on the
  localhost API is a documented single-user decision; code style/formatting; the heuristic
  nature of idea scoring. If you think a documented decision in `DECISIONS.md` is itself wrong,
  say so once, briefly, in the "Design concerns" section — don't file it as a bug.
- **Severity scale:** `Critical` (security invariant broken, data loss, or silent double
  external write) · `High` (correctness bug on a core path) · `Medium` (edge case, resource
  leak, race only under load) · `Low` (docs/behavior mismatch, minor).

---

## 5. How to give the feedback back to me

Produce **one Markdown report** and make it retrievable in the way that fits your environment:

- **Preferred:** write it to `docs/reviews/codex-findings.md`, commit on a branch
  `codex/adversarial-review`, push, and open a PR against
  `claude/build-brief-implementation-dbre2i`. Put any demonstrating tests in the same branch
  under `tests/` / `e2e/` so I can run them.
- **If you can't push:** paste the full report back as your final message.

Use exactly this structure so I can triage fast:

```
# Codex adversarial review — AgenticOS Cockpit

## Summary
- Reviewed commit: <sha>
- Verdict in one line.
- Counts: Critical N · High N · Medium N · Low N.
- What I ran (setup/tests/live attacks) and the environment.

## Findings (ranked, most severe first)
### F1. <one-line title> — <Critical|High|Medium|Low> — <CONFIRMED|SUSPECTED>
- Invariant / property violated: <which item from §2, or new>
- Location: <file:line>, <file:line>
- Failure scenario: <concrete inputs/state → observed wrong behavior>
- Reproduction: <exact commands / request / test name>, or traced call chain
- Impact: <what an attacker or unlucky user gets>
- Suggested fix: <1–2 sentences>
- Evidence: <test file path / log excerpt / screenshot>

### F2 …

## What I could NOT break
- Invariants I actively attacked and they held (list each, with how you attacked it).
  This section is required — it tells me what's actually validated vs. merely unchallenged.

## Design concerns (not bugs)
- Architectural/threat-model observations worth a decision, with a recommendation.

## Tests added
- Paths + one line each; whether they currently pass or fail against the branch.
```

**Ranking rule for the report:** order findings by (severity, then confidence). Every CONFIRMED
finding must include a reproduction I can run. If you found nothing at a given severity, say so
explicitly rather than padding.

Begin by cloning the branch, building, and confirming the app boots — then go after §3.1 and
§3.2 first.
