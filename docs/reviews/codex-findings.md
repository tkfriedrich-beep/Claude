# Codex adversarial review — AgenticOS Cockpit

## Summary
- Reviewed commit: `027c179e2507213560c8e4beeddaeaabf57de593`
- Verdict in one line: The control plane has two critical safety failures—cross-restart duplicate external writes and a symlink-based filesystem escape—plus a broken run-claim CAS that can execute one run twice.
- Counts: Critical 2 · High 2 · Medium 2 · Low 0.
- What I ran (setup/tests/live attacks) and the environment: I attempted the required clone first with `git clone --branch claude/build-brief-implementation-dbre2i https://github.com/tkfriedrich-beep/Claude.git`, but this execution environment has no DNS/network path to GitHub (`Could not resolve host: github.com`). I therefore could not run `make setup`, boot the services, or execute the existing suites locally. I inspected the exact PR head through the authenticated GitHub connector and traced the critical paths end-to-end. I also attempted to create `codex/adversarial-review`, but the GitHub integration returned HTTP 403 for branch creation. Findings marked CONFIRMED below are demonstrated by deterministic traced execution paths; no finding relies on style or vague speculation.

## Findings (ranked, most severe first)
### F1. A process crash after an external effect but before the completion commit silently permits the effect to fire again — Critical — CONFIRMED
- Invariant / property violated: Security invariant 3; correctness invariants 10 and 11.
- Location: `services/control-plane/src/cockpit/gateway.py:195-202`, `services/control-plane/src/cockpit/gateway.py:428-479`, `services/control-plane/src/cockpit/worker.py:713-737`, `services/control-plane/src/cockpit/api/runs.py:179-191`.
- Failure scenario: An approved, non-idempotent external write enters `_execute`. The gateway marks the `ToolCall` `running`, invokes the connector, and the target system performs the real effect. The process is killed after `connector.execute(...)` returns but before the surrounding SQLAlchemy transaction commits the `completed` status and output. On restart, recovery marks the run `interrupted`. The user resumes it. The skill re-enters from the top and calls the same tool with the same idempotency key. The existing row is either absent or still `running`; `call_tool` only replays rows whose status is exactly `completed`, so it falls through and invokes `_execute` again. The external effect fires twice.
- Reproduction: Use any connector test double whose `execute` appends to a durable file or external counter, then terminate the process immediately after `_run_connector` returns and before the session commit. Restart, POST `/api/v1/runs/{id}/resume`, and observe the counter increment twice. The decisive traced chain is `call_tool` → existing status check (`completed` only) → `_execute` → connector effect → crash before commit → recovery to `interrupted` → resume to `queued` → skill replay → `_execute` again.
- Impact: Duplicate emails, duplicate webhook actions, duplicate calendar changes, duplicate purchases, or any other non-idempotent mutation. This directly contradicts the product’s strongest safety claim.
- Suggested fix: Persist an execution intent/lease before dispatch and use a connector-level idempotency token or outbox/inbox protocol. Treat `running` after restart as an ambiguous outcome requiring reconciliation or human review, never automatic replay for non-idempotent external writes.
- Evidence: `gateway.call_tool` only short-circuits `ToolCallStatus.COMPLETED`; `_execute` performs the connector call before the completion state is durably committed. The restart message claims completed writes will not re-fire, but it does not handle ambiguous in-flight writes.

### F2. `local_files.write` follows a final-path symlink outside the configured roots — Critical — CONFIRMED
- Invariant / property violated: Security invariant 6.
- Location: `services/control-plane/src/cockpit/connectors/local_files.py:141-176`, `services/control-plane/src/cockpit/connectors/base.py:132-143`.
- Failure scenario: Create an allowed root `/vault`, create `/vault/escape.md` as a symlink to `/tmp/outside.md`, and invoke `local_files.write` with `path=/vault/escape.md`. `_write` validates only `raw_path.parent` with `contain_path`, then reconstructs `path = parent / raw_path.name`. It never resolves or validates the final target. `path.write_text(...)` follows the symlink and writes `/tmp/outside.md`.
- Reproduction: `mkdir -p /tmp/vault; ln -s /tmp/outside.md /tmp/vault/escape.md`, configure `/tmp/vault` as an allowed root, approve a `local_files.write` call for `/tmp/vault/escape.md`, then `cat /tmp/outside.md`. The content supplied to the tool appears outside the root.
- Impact: An attacker or malicious retrieved instruction can overwrite arbitrary files writable by the cockpit process, including shell startup files, application configuration, or user documents outside the vault.
- Suggested fix: Open the target with no-follow semantics and verify the opened file descriptor’s resolved location, or reject existing symlinks and perform an atomic `openat`/directory-fd write beneath a trusted root. Re-check after creation to address TOCTOU.
- Evidence: Parent containment is checked, but the final path component is not resolved before `write_text`.

### F3. `claim_next_run` is not a compare-and-swap and can claim the same queued run multiple times — High — CONFIRMED
- Invariant / property violated: Correctness invariant 11 and prioritized concern 6.
- Location: `services/control-plane/src/cockpit/worker.py:688-710`, `services/control-plane/src/cockpit/worker.py:744-768`.
- Failure scenario: Two worker iterations or processes select the same oldest row with `status='queued'`. The first update sets only `worker_claim` and `heartbeat_at`; it does not change `status`. The second update still satisfies `WHERE id=? AND status='queued'`, returns `rowcount=1`, and also claims the same run. Both callers then schedule `run_one(run.id)` and process it concurrently.
- Reproduction: Open two independent async sessions, synchronize them after the initial `SELECT`, then call the update in both. Both updates succeed because the predicate remains true after the first commit. In the actual loop, the producer also keeps claiming immediately without acquiring the semaphore first, making duplicate task creation possible under concurrent claimers or multiple processes.
- Impact: One run can execute twice, produce duplicate artifacts/memories, race FSM transitions, and amplify the duplicate-external-write defect.
- Suggested fix: Atomically transition `queued` to a distinct claimed/triaging state in the same `UPDATE ... WHERE status='queued'`, or use `UPDATE ... RETURNING` with a unique lease token and verify that token before processing.
- Evidence: The purported CAS changes `worker_claim` but leaves the CAS predicate (`status='queued'`) unchanged.

### F4. Two chat approvals consume all default worker slots for up to ten minutes — High — CONFIRMED
- Invariant / property violated: Availability/core execution property; prioritized concern 2.
- Location: `services/control-plane/src/cockpit/worker.py:512-627`, `services/control-plane/src/cockpit/worker.py:744-777`.
- Failure scenario: With default `worker_concurrency=2`, start two chat runs whose provider requests approval-gated tools. Each task enters `_chat_permission`, transitions to `awaiting_approval`, then polls `_wait_for_approval` for up to 600 seconds. The semaphore is held for the entire `processor.process(...)` call, so both slots remain occupied. Every unrelated queued run is starved until one approval resolves or times out.
- Reproduction: Set concurrency to 2, submit two chat runs that trigger approvals, leave both pending, then submit a third run. The third run may be claimed and represented by an asyncio task, but cannot enter `run_one` past the semaphore until a waiter exits.
- Impact: A user can accidentally freeze all execution by leaving two approval cards unanswered. A malicious or buggy provider can cause a trivial local denial of service.
- Suggested fix: Park chat runs like skill runs: persist the pending provider/tool continuation, release the worker slot and DB session, and requeue only after approval resolution.
- Evidence: `_wait_for_approval` is called inside `run_one` while `async with semaphore` remains active.

### F5. SSE backfill can duplicate events and can omit more than 500 historical events — Medium — CONFIRMED
- Invariant / property violated: Event ordering/delivery integrity; prioritized concern 3.
- Location: `services/control-plane/src/cockpit/api/runs.py:244-286`, `services/control-plane/src/cockpit/events.py:94-107`.
- Failure scenario: The SSE generator subscribes to the live queue before querying the database for backfill. Any event committed after subscription but before the backfill query completes can be returned by the DB and also remain queued, so the client receives it twice. Separately, backfill is hard-limited to 500 rows and then immediately switches to live delivery; if more than 500 persisted events existed after the cursor before subscription, rows 501+ are never sent on that connection.
- Reproduction: Connect with `Last-Event-ID`, concurrently emit an event while the backfill query is running, and observe the same event ID once from backfill and once from the queue. For omission, create 501+ events after the cursor before opening the stream; only the first 500 are backfilled and the remainder are not drained from storage.
- Impact: UI timelines can show duplicate actions or silently miss audit events, undermining reconstructability and operator trust.
- Suggested fix: Establish a high-water mark transactionally, backfill through that mark with pagination, then consume live events strictly above it with event-ID deduplication.
- Evidence: Subscription precedes backfill and there is no high-water mark or dedupe set; the DB query uses `.limit(500)` once.

### F6. EventBus retains one lock and one run-key entry per historical run forever — Medium — CONFIRMED
- Invariant / property violated: Resource-bounded operation; prioritized concern 3.
- Location: `services/control-plane/src/cockpit/events.py:86-100`, `services/control-plane/src/cockpit/events.py:109-142`.
- Failure scenario: Every call to `emit` evaluates `self._seq_locks[run_id]`, permanently inserting a lock into the `defaultdict`. Every run-specific subscription evaluates `self._by_run[run_id]`; `unsubscribe` removes the queue but never removes the empty set or key. Creating many runs causes both dictionaries to grow monotonically.
- Reproduction: Emit one event for 100,000 unique run IDs and inspect `len(bus._seq_locks)`. It equals 100,000. Subscribe/unsubscribe once for each run and inspect `len(bus._by_run)`; empty entries remain.
- Impact: Long-lived installations accumulate avoidable memory indefinitely. The leak is modest per run but guaranteed and unbounded.
- Suggested fix: Remove empty run subscription sets on unsubscribe and evict per-run locks after terminal state once no emitter/subscriber references remain, or use a bounded lock registry.
- Evidence: Neither dictionary has an eviction path.

## What I could NOT break
- Safe Mode policy ordering: I traced `policy.evaluate` across write paths. The Safe Mode denial occurs before autonomy and allowlist grants for tools marked `external_side_effects=True`. I did not find a policy branch that directly permits such a tool while Safe Mode is enabled. This is not a runtime validation of dishonest connector metadata.
- Manifest-level `approval: required`: In `gateway.call_tool`, this can tighten an `ALLOW` decision into `REQUIRE_APPROVAL`; it does not loosen a denial.
- Basic IDOR checks on reviewed run, artifact, memory, event, project, people, and list endpoints: the reviewed endpoints either scope queries by `workspace_id` or fetch by ID and compare ownership before returning/mutating. I did not review every API module deeply enough to claim the entire invariant is proven.
- Obvious frontend HTML injection through the shared Markdown renderer: raw `&`, `<`, and `>` are escaped before the renderer introduces its own fixed tags. The Knowledge snippet path also escapes these characters before replacing the special highlight markers. I did not execute browser payloads because the app could not be built in this environment.
- Direct `run.status = ...` assignment: repository code search returned no direct assignment. Reviewed status changes route through `state_machine.transition`.

## Design concerns (not bugs)
- The single-process in-memory worker and event bus are presented as locally durable, but several guarantees implicitly assume one process. If multi-process execution is a foreseeable scaling path, the threat model should explicitly state that it is unsupported until leases, distributed event delivery, and transactional outbox semantics exist.
- Trusting connector manifests to truthfully declare `external_side_effects`, `idempotent`, and `supports_dry_run` is a large part of the security boundary. Treat installation or modification of manifests/connectors as privileged code installation, not ordinary configuration.
- A dry-run is only side-effect-free by connector convention. For third-party connectors, preview execution should ideally use a separate explicit preview method/capability rather than invoking the same executor with a boolean flag.

## Tests added
- None. I could not clone or execute the repository because this environment cannot resolve GitHub, and the GitHub integration denied branch creation with HTTP 403. The report provides exact deterministic reproductions for each confirmed finding, but no unrun test files were committed.
