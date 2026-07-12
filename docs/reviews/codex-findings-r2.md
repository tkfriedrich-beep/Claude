# Codex adversarial review (round 2) — AgenticOS Cockpit

Second-pass review commissioned via `docs/reviews/ADVERSARIAL_REVIEW_PROMPT_R2.md`, whose brief
was explicitly to attack the round-1 fixes (ADR-013) and the connector-boundary hardening
(ADR-014) rather than re-scan the whole tree.

## Summary

- Reviewed commit: `edb2e6d` (branch `claude/build-brief-implementation-dbre2i`).
- Verdict in one line: the round-1/ADR-014 fixes hold at their center but leak at the seams — a
  Safe-Mode bypass via an allow rule, a dry-run that still made a real HTTP call, a hardlink
  variant of the symlink escape, and glob/symlink traversal in discovery were the sharpest.
- Counts: Critical 1 · High 5 · Medium 4 · Low 2.
- Every finding below was re-verified against the actual code on-branch (not only the reviewer's
  isolated repro) before being fixed. All 12 are CONFIRMED and FIXED, each with a regression test
  in `services/control-plane/tests/test_review_r2_fixes.py`.

## Findings (ranked, most severe first)

### F1. A user-created `allow` rule overrides Safe Mode for an untrusted external read — High — CONFIRMED · FIXED
- Invariant violated: Safe Mode is an emergency gate (THREAT_MODEL); ADR-014 promised "Safe Mode
  denies untrusted external calls outright."
- Location: `services/control-plane/src/cockpit/policy.py` (untrusted-external-read branch).
- Failure scenario: An untrusted connector's read tool (`external_side_effects=True`,
  `trusted=False`) with a matching `allow` rule was evaluated by testing the allow rule *before*
  Safe Mode, so the external call was permitted even with Safe Mode engaged.
- Fix: Safe Mode is now checked **before** the allow-rule loop in that branch; an allow rule can
  never re-enable a user-registered connector's external call while Safe Mode is on.

### F2. `n8n.preview()` still performed a real HTTP POST during a "dry run" — High — CONFIRMED · FIXED
- Invariant violated: a dry-run/preview must be side-effect free (ADR-014).
- Location: `services/control-plane/src/cockpit/connectors/n8n.py`.
- Failure scenario: the "preview" path posted to the webhook with a `dry_run: true` body. A
  hostile or buggy workflow ignores that flag and performs the real effect — so previewing a
  draft/shadow action could fire it. (This was a hole flagged in our own round-2 prompt but
  shipped anyway.)
- Fix: `preview()` now returns a **local** description of the request that would be sent
  (`"Would POST to …"` plus the truncated payload) and makes no network call at all. Only
  `execute()` ever contacts the webhook.

### F3. `local_files.write` follows a hardlink out of the workspace — High — CONFIRMED · FIXED
- Invariant violated: filesystem containment (security invariant 6). The ADR-013 fix closed
  *symlink* escape but not hardlinks.
- Location: `services/control-plane/src/cockpit/connectors/local_files.py`.
- Failure scenario: `ln /etc/target /vault/inside.md` (a hardlink) shares an inode with a file
  outside the roots. `contain_write_target` sees a normal in-root path (no symlink), so the write
  lands on the outside inode.
- Fix: `_write` opens with `O_NOFOLLOW | O_CLOEXEC` and, before truncating, rejects any file whose
  `st_nlink > 1` (a hardlink to a possibly-outside inode). The nlink check precedes the truncate,
  so a rejected write does no damage.

### F4. `../*` glob and symlinked directory entries escape the roots during discovery — High — CONFIRMED · FIXED
- Invariant violated: filesystem containment on the *read* side (list/search/reindex).
- Location: `local_files.py` (`_list`, `_search`), `knowledge.py` (reindex), `obsidian.py`
  (`_iter_notes`).
- Failure scenario: `local_files.list` with `glob="../*"` enumerated a parent directory; and a
  symlinked entry *inside* a root (pointing outside) was followed by `glob`/`rglob`, leaking
  outside file contents into listings, search hits, and the FTS index.
- Fix: a new `safe_glob_pattern()` rejects `..`/absolute patterns; a new realpath-based
  `is_within_roots()` re-checks every discovered path, and each of list/search/reindex/vault-iter
  now skips `p.is_symlink()` and any entry that resolves outside the roots.

### F5. Connector error text and edited approval input could persist secrets unredacted — Medium — CONFIRMED · FIXED
- Invariant violated: secrets never land raw in the DB/audit trail.
- Location: `services/control-plane/src/cockpit/gateway.py` (preview-error path),
  `services/control-plane/src/cockpit/api/approvals.py` (approval edit path).
- Failure scenario: (a) a connector exception whose message echoed a request/response body was
  stored verbatim in `approval.diff_preview`; (b) the approval "edit input" path persisted the
  user-supplied `edited_input` without the redaction the original `input` gets.
- Fix: preview-error text is wrapped in `redact_text(...)`; `edited_input` is passed through
  `redact(...)` before persistence, masking credential-shaped values while leaving ordinary edits
  intact.

### F6. n8n idempotency key ignored the payload, so two distinct calls collided — Medium — CONFIRMED · FIXED
- Invariant violated: idempotency keys must uniquely identify an external mutation (invariant 6).
- Location: `services/control-plane/src/cockpit/connectors/n8n.py`.
- Failure scenario: the key was `sha256(run_id | tool_id)` only. Two different calls to the same
  webhook within one run produced the **same** key; a caching/idempotent workflow returned the
  first call's response for the second — a silent no-op reported as success.
- Fix: the key now includes a canonical (`sort_keys=True`) serialization of the validated input:
  `sha256(run_id | tool_id | canonical_input)`. Same input → stable key; different input →
  different key.

### F7. `obsidian.write_note` could write into another root via `..`/absolute path — High — CONFIRMED · FIXED
- Invariant violated: an Obsidian write must stay inside the vault.
- Location: `services/control-plane/src/cockpit/connectors/obsidian.py`.
- Failure scenario: `_delegate_write` passed the note path to the shared local-files helper, which
  checks *all* configured roots. A `path` of `../bizideas/x.md` (or an absolute path) therefore
  landed in the ideas folder or `data/local/` — outside the vault the user thought they were
  editing.
- Fix: `_delegate_write` rejects absolute paths and any `..` component, then delegates with the
  vault as the **only** root (`replace(ctx, roots=[vault])`).

### F8. Global connector singletons race workspace config — External payloads could route to the wrong endpoint — High — CONFIRMED · FIXED (proportionately)
- Invariant violated: every action uses *its* workspace's configuration (invariant 7).
- Location: `services/control-plane/src/cockpit/registry.py` (singletons), `gateway.py`, `n8n.py`,
  `mcp.py`.
- Failure scenario: connectors are process-global singletons; `refresh_runtime_config(ws)`
  overwrites each singleton's `runtime_config`. A run for workspace A that is policy-checked
  against A's DB row could execute against B's URL if B refreshed the singleton in between, so A's
  payload POSTs to B's webhook.
- Fix: the gateway threads **this workspace's** `Connector.config` (from the DB row) through
  `ExecutionContext.config`; n8n `_webhooks(ctx)` and mcp `_servers(ctx)` prefer `ctx.config` over
  the singleton. Execution routes to the correct workspace endpoint or fails closed if the tool is
  not in that workspace's own config. Dormant in the single-user MVP (one workspace) but fixed so
  the guarantee is real. Manifest *resolution* (`find_tool`) still reads the singleton; acceptable
  because n8n/mcp tools always require approval and the approval card's preview/target are built
  from the workspace config — documented as a known bound.

### F9. A denied chat tool left ghost SSE events after rollback — Medium — CONFIRMED · FIXED
- Invariant violated: persisted events are the source of truth; a rolled-back action must leave no
  trace.
- Location: `services/control-plane/src/cockpit/worker.py` (`_chat_permission`), `gateway.py`.
- Failure scenario: the ADR-013 F4 fix denied approval-gated chat tools, but only *after*
  `call_tool` had already emitted `TOOL_PROPOSED`/`APPROVAL_REQUIRED` and published them to live
  SSE subscribers. The subsequent rollback removed the DB rows but the events had already been
  delivered — ghost timeline entries.
- Fix: a new read-only `gateway.preflight()` makes the allow/deny decision **without** creating any
  ToolCall/Approval/event. `_chat_permission` calls `preflight` first and denies non-allowed tools
  with zero persisted or published state; only an allowed tool proceeds to `call_tool`.

### F10. Resuming a skill run duplicated its artifacts and proposed memories — Medium — CONFIRMED · FIXED
- Invariant violated: idempotent result persistence across crash/resume.
- Location: `services/control-plane/src/cockpit/worker.py` (`_persist_result`), `models.py`.
- Failure scenario: a resumed run re-executes from the top and re-ran `_persist_result`, inserting
  a *second* set of artifact and proposed-memory rows.
- Fix: `Memory` gains a `run_id`; `_persist_result` first deletes this run's artifacts and its
  still-**proposed** memories (+ sources), then re-inserts — so a replay replaces rather than
  duplicates. Already-approved memories are untouched. Schema delta in migration `0003`.

### F11. `run_one` did not re-verify claim ownership after acquiring the semaphore — Low — CONFIRMED · FIXED
- Invariant violated: a run executes at most once (invariant 11); defense in depth for
  multi-process.
- Location: `services/control-plane/src/cockpit/worker.py` (`run_one`).
- Failure scenario: a task that waited on the worker semaphore could, in a multi-process
  deployment, have had its claim cleared/reassigned by another process's startup recovery or a
  re-queue while it waited — then execute anyway.
- Fix: a pure `claim_still_owned(run, worker_id)` predicate re-checks ownership after the semaphore
  and skips the run if another worker owns the claim while it is still `queued`. Dormant in the
  single-process MVP; makes the guarantee robust.

### F12. A lock-eviction race could assign two events the same `(run_id, seq)` — Low — CONFIRMED · FIXED
- Invariant violated: per-run event sequence numbers are unique and monotonic (SSE cursor
  integrity).
- Location: `services/control-plane/src/cockpit/events.py`, `models.py`.
- Failure scenario: the per-run seq lock is dropped on a terminal event (ADR-013 F6). A late event
  after that eviction could recompute `max(seq)` concurrently with another emit and collide.
- Fix: a `UNIQUE(run_id, seq)` constraint on `run_events` (migration `0003`) makes a duplicate
  impossible at the DB, and `emit()` now assigns the seq inside a `SAVEPOINT` and retries on
  `IntegrityError` (up to 8 attempts), so a collision is resolved transparently.

## What was NOT changed (and why)

- Manifest *resolution* for runtime-registered tools still reads the global singleton (F8): a full
  fix needs per-workspace registries, which is disproportionate for a single-user MVP where these
  tools are always approval-gated. Documented as a bound, not silently ignored.
- F11 remains a defensive re-check; true multi-process safety needs a leased-claim protocol
  (deferred, noted in ROADMAP).
