# Adversarial code review — AgenticOS Cockpit — ROUND 2

You are a skeptical staff-level security + systems reviewer. This is the **second** adversarial
pass. Round 1 found six real defects; the **same AI author** then fixed all six and added two
hardening changes **and wrote its own tests for them.** That is exactly the code you should
distrust most. Your job is to **break the fixes** and the new trust/preview boundary — prove
they are incomplete, defeatable, or that they introduced new bugs. A pass that only re-confirms
"the fix is there" is a failed review; show where it *isn't* enough.

Earn credit only for defects you can **demonstrate** (failing test, reproduction, or traced
path). No style nitpicking. Label every finding **CONFIRMED** or **SUSPECTED**.

---

## 1. Repository & setup

- **Repo:** `github.com/tkfriedrich-beep/Claude`, branch `claude/build-brief-implementation-dbre2i`
  (PR #5). Review at **HEAD = `d8e9c03`** (or later).
- **Read first, so you don't re-report settled ground:**
  - `docs/reviews/codex-findings.md` — round-1 report (F1–F6).
  - `DECISIONS.md` **ADR-013** (round-1 fixes) and **ADR-014** (the two hardening changes).
  - `services/control-plane/tests/test_review_fixes.py` and `tests/test_hardening.py` — the
    author's own regression tests. **Assume these tests are too weak and miss the real edge
    cases.** Your job is to find the case they don't cover.
  - `BUILD_BRIEF.md` (governing contract), `docs/THREAT_MODEL.md`, `docs/ARCHITECTURE.md`.
- **Build & run** (no Docker):
  ```bash
  make setup && make demo && make dev        # control plane :8787, web :3000
  cd services/control-plane && uv run pytest -q          # 106 tests
  cd apps/web && PLAYWRIGHT_CHROMIUM_PATH=/opt/pw-browsers/chromium pnpm exec playwright test
  ```
  uv fallback: `docs/RUNBOOK.md`. Claude runtime needs `ANTHROPIC_API_KEY`; everything else runs
  credential-free. Confirm you can build, migrate (`alembic upgrade head` → head is
  `0002_connector_tool_trusted`), seed, and boot before attacking.

**Out of scope (do not spend time here):** the six round-1 findings are fixed — only report them
if you can show the fix is *incomplete or defeatable*, not that the class exists. Intentional
mocks (Google/Notion/GitHub), provider stubs (OpenAI/Ollama/LangGraph), the no-auth localhost
API (documented single-user decision), and code style are out of scope.

---

## 2. Primary targets — attack the fixes and the new boundary

These are the newest, self-reviewed, self-tested changes. Go here first.

### A. F1 fix — durable intent + no auto-replay (gateway.py)
The fix commits a `running` tool_call before dispatching a non-idempotent external write, and
`call_tool` refuses to replay a `running` non-idempotent external tool on resume
(`ToolGateway.call_tool` / `_execute` in `cockpit/gateway.py`).
- Is the pre-dispatch `session.commit()` reached on **every** non-idempotent external path,
  including through `edited_input` (approval-edited input changes the executed args — does the
  `running`-guard still key on the right idempotency row)? Trace the edited-input + resume combo.
- Is there still a window? The commit persists `running`, but what if the crash happens
  *between* the connector effect and… nothing — is `running`→`failed` on resume correct, or can
  a run get wedged (stuck `executing`/`awaiting_approval`) so the user can neither resume nor
  cancel? Kill `-9` mid-write for real and inspect FSM state.
- The idempotent/local path is *allowed* to re-run. Can a skill's non-tool local state (counters,
  in-memory dedup, artifact numbering) be corrupted by the full re-execution on resume?
- Does the mid-`_execute` commit prematurely persist partial run state that a later failure
  can't roll back (events emitted, `run.steps` incremented, then failure)?

### B. F2 fix — symlink write guard (`contain_write_target` in connectors/base.py)
- **TOCTOU:** the guard resolves the target, then `_write` calls `write_text` later. Swap a
  benign path for a symlink between check and write (two rapid calls / a race) — does it escape?
- **Hardlinks:** a hardlink inside a root to a file outside is not a symlink. Can you overwrite
  an outside inode? (Expected: yes — is it documented, or a silent hole?)
- `os.path.realpath` edge cases: a **symlinked parent** that resolves back inside a root but via
  an outside path; `..` segments in `name`; unicode/case tricks; a root that is itself a symlink;
  very deep symlink chains; a target whose parent doesn't exist yet.
- Obsidian delegates writes to the local-files helper — confirm the guard actually runs for
  `obsidian.write_note` and can't be bypassed with an absolute `path` or `../` in the note path.

### C. F3 fix — claim CAS on `worker_claim IS NULL` (worker.py + state_machine.py)
- **New stranding bug?** A run claimed then crash *before* `process()` flips it to `triaging`
  stays `queued` with a stale `worker_claim`. Startup clears queued claims — but is that clear
  racy against a live claimer in the same process, or against the scheduler? Can a run become
  permanently unclaimable?
- Does **every** path that re-queues a run clear `worker_claim`? Check approval-resolve requeue,
  `/runs/{id}/resume`, scheduler paths, and the FSM `to == QUEUED` hook. Find one that doesn't.
- Multi-process: the guard is per-row CAS, but startup does a blanket
  `UPDATE … worker_claim=NULL WHERE status=queued` — with two processes, can process B's startup
  clear a run process A just claimed? (The MVP is single-process, but the brief anticipates
  scaling — flag it as a design bug if real.)
- Under semaphore saturation, confirm the loop no longer spawns duplicate tasks for one run
  (the original F3 symptom). Try to still make it double-execute.

### D. F4 fix — chat denies approval-gated tools (worker.py `_chat_permission`)
- The `ApprovalPending` branch now `session.rollback()`s and denies. Does the rollback discard
  *other* legitimately-pending state on that session (events, the run's status transition),
  corrupting the run or losing audit events?
- Is there any remaining path where a chat turn blocks a worker slot on I/O or a lock?

### E. ADR-014 — dry-run as a distinct `preview()` capability
- The real guarantee is meant to be gateway routing (`preview()` vs `execute()`), with
  `assert not ctx.dry_run` as a backstop. **Python strips `assert` under `-O`/`PYTHONOPTIMIZE`.**
  Is there any gateway path that can call `execute()` with `dry_run=True`? If the routing is the
  only guarantee, prove it holds; if the asserts matter, show the `-O` hole.
- Is every `preview()` genuinely side-effect-free? `n8n.preview()` **posts to the external
  webhook** with `dry_run:true` — that's an external call during a "preview," trusting the
  workflow's contract. Is that acceptable, or a side effect masquerading as a preview? What about
  a webhook that ignores the `dry_run` flag?
- Can a tool reach a dry-run with `supports_dry_run=true` but no real `preview()` (a lying
  manifest / a runtime-registered n8n webhook with `supports_dry_run:true`)? Confirm it fails
  closed (no effect), not open.

### F. ADR-014 — untrusted runtime-registered tools
- The gateway builds its `ToolSpec.trusted` from the connector's **live manifest**
  (`find_tool` → `list_tools`), while the DB `connector_tools.trusted` column is for display.
  Can these diverge such that the UI shows "trusted" but the gateway treats it untrusted, or vice
  versa? Is the gateway's source authoritative and un-spoofable via the registration API?
- Try to get an **untrusted** external tool to **auto-run** (no approval): via a skill allowlist
  (does a skill manifest referencing `n8n.*`/`mcp.*` bypass the untrusted gate?), via draft mode
  + `supports_dry_run`, via an `allow` policy rule with a broad `connector_slug` match, via
  autonomy level 5, or via the read path (untrusted external *read*).
- Register an MCP server / n8n webhook through `POST /api/v1/connectors` that **lies** about
  `read_only` and confirm it still cannot auto-run. Then confirm Safe Mode denies it.
- Does the `connector_tools.trusted` migration (`0002`) behave on a DB created by the *old*
  `0001` (column absent) as well as a fresh DB (column present via create_all)? Try both.

---

## 3. Also fair game (regression from the changes)

Re-run the round-1 attack surface to confirm the fixes didn't reopen anything, plus: policy
matrix completeness with the new untrusted gate inserted (did it change any *trusted* tool's
outcome?), SSE dedupe/pagination correctness (F5) under concurrent emit + reconnect, event-bus
eviction (F6) racing a late straggler emit after a terminal event, and IDOR across the API
modules not deeply checked in round 1 (artifacts download, memories, automations run-now).

---

## 4. Rules of engagement

- **Prove it.** Failing test (pytest under `services/control-plane/tests/`, or Playwright/vitest),
  a reproduction with exact commands/requests, or a precise traced call chain with `file:line`.
  Label **CONFIRMED** (reproduced/traced end-to-end) vs **SUSPECTED**.
- **Attack at runtime.** Boot demo mode; `kill -9` the control plane mid-write and resume; race
  two registrations; swap a symlink under a pending write; open concurrent SSE + reconnect;
  register a lying n8n/MCP tool and try to auto-run it.
- **Don't fix — report.** One- or two-sentence suggested fix per finding.
- **Severity:** `Critical` (security invariant broken / data loss / silent double external write
  / untrusted tool auto-runs / write escapes roots) · `High` (core-path correctness, or a
  round-1 fix defeatable) · `Medium` (edge case, race under load, leak) · `Low` (doc/behavior
  mismatch).

---

## 5. How to give the feedback back to me

Produce **one Markdown report**:
- **Preferred:** write it to `docs/reviews/codex-findings-r2.md`, commit on branch
  `codex/adversarial-review-r2`, push, open a PR against `claude/build-brief-implementation-dbre2i`,
  and put any demonstrating tests in that branch under `tests/` / `e2e/`.
- **If you can't push:** paste the full report as your final message.

Use exactly this structure:

```
# Codex adversarial review R2 — AgenticOS Cockpit

## Summary
- Reviewed commit: <sha>
- One-line verdict.
- Counts: Critical N · High N · Medium N · Low N.
- What I ran (setup / tests / live attacks) and the environment.

## Findings (ranked, most severe first)
### F1. <title> — <Critical|High|Medium|Low> — <CONFIRMED|SUSPECTED>
- Which fix / invariant it defeats: <round-1 F#, ADR-014 area, or new>
- Location: <file:line>, <file:line>
- Failure scenario: <concrete inputs/state → observed wrong behavior>
- Reproduction: <exact commands / request / test name> or traced call chain
- Impact: <what an attacker or unlucky user gets>
- Suggested fix: <1–2 sentences>
- Evidence: <test path / log excerpt / screenshot>

## Fixes I tried hard to break but couldn't
- For each round-1 fix (F1–F6) and each ADR-014 change: how you attacked it and why it held.
  This section is REQUIRED — it tells me which fixes are actually validated.

## New design concerns (not bugs)
- With a recommendation.

## Tests added
- Paths + one line each; pass/fail against the branch.
```

**Ranking:** severity, then confidence. Every CONFIRMED finding needs a runnable reproduction.
State explicitly if a severity band is empty rather than padding.

Start with §2E (the `-O` assert / preview side-effect question) and §2F (getting an untrusted
tool to auto-run) — those are the highest-value places the author's own fix is most likely thin.
