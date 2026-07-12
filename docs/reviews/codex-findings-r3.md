# Codex adversarial review R3 — AgenticOS Cockpit

## Summary
- Reviewed commit: `e853a3c93b0c4cfc65a2c4625d16a76d9bdec0cf` (the supplied archive states that the application code is identical to `f07a94c`, with the Round-3 review prompt added at the archive tip).
- The new web-egress path is exploitable, and several Round-2 fixes protect only the exact case covered by their tests: I reached loopback through `web.fetch`, bypassed Safe Mode and the crash replay guard through workspace/global MCP manifest divergence, escaped a filesystem root through a parent-symlink race, and demonstrated ten additional integrity, secret-handling, migration, and concurrency failures.
- Counts: Critical 5 · High 6 · Medium 2 · Low 0.
- What I ran (setup / tests / live attacks) and the environment: Linux x86_64, Python 3.13.5, SQLite 3.46.1, uv 0.10.0, Node 22.16.0, pnpm 10.4.1. `make setup` succeeded and Alembic reached `0003_memory_run_id_event_seq_unique`; `make demo` seeded and executed real demo runs; the control plane booted on `:8787`, `GET /api/v1/health` returned 200, and the Next.js app returned 200 on `:3000`. The unmodified Python suite passed (`140 passed`), the four author regression files passed (`53 passed`), Vitest passed (`6 passed`), and Ruff, Mypy, TypeScript, and ESLint were clean. The added adversarial file produced `15 failed`, each at its intended safety assertion. Playwright could not be evaluated because this runner blocks Chromium navigation to localhost with `net::ERR_BLOCKED_BY_ADMINISTRATOR`; the control-plane and web processes themselves were reachable with curl. I also ran live socket-based DNS-rebinding, oversized-response, filesystem-race, API-config, Alembic-upgrade, and concurrent event-emission attacks. The environment could not resolve `github.com`, and the available GitHub integration returned HTTP 403 when I attempted to create `codex/adversarial-review-r3`, so I could not push a review branch or open the preferred PR.

## Findings (ranked, most severe first)

### F1. DNS rebinding makes `web.fetch` connect to loopback after the SSRF check — Critical — CONFIRMED
- Which fix / invariant / new surface it defeats: ADR-016’s SSRF boundary and the new `web.fetch` security contract.
- Location: `services/control-plane/src/cockpit/connectors/web.py:62-93`, `services/control-plane/src/cockpit/connectors/web.py:221-239`.
- Failure scenario: `assert_public_http_url()` resolves `rebind.test` and sees only a public address. `httpx` then performs an independent DNS resolution while opening the connection. A hostname that returns `93.184.216.34` to the guard and `127.0.0.1` to the connect lookup passes validation and reaches a local service. The reproduced response body was `INTERNAL_ONLY=local-control-plane-secret`.
- Reproduction: `cd services/control-plane && uv run pytest -q tests/test_adversarial_r3.py::test_r3_dns_rebinding_must_not_reach_loopback`. The test starts a real loopback HTTP server, flips DNS between the two lookups, calls the actual connector, and fails because no `ConnectorError` is raised and the local server receives the request.
- Impact: A URL controlled by search results, user input, or a fetched page can reach localhost services and, in cloud/container environments, metadata endpoints. This is credential theft and lateral access through a tool that auto-runs as a trusted read.
- Suggested fix: Resolve once, validate every address, and pin the actual connection to a selected validated IP while sending the original hostname as SNI/Host; repeat that process for every redirect. Do not rely on a preflight DNS lookup followed by a normal hostname connection.
- Evidence: `services/control-plane/tests/test_adversarial_r3.py::test_r3_dns_rebinding_must_not_reach_loopback`; `r3_adversarial_tests.log` (`Failed: DID NOT RAISE ConnectorError`).

### F2. Global MCP manifest state bypasses Safe Mode and the crash replay guard for another workspace’s remote tool — Critical — CONFIRMED
- Which fix / invariant / new surface it defeats: Round-2 F8/ADR-015 workspace isolation, Safe Mode, and Round-1 F1’s “no silent double external write” guarantee.
- Location: `services/control-plane/src/cockpit/gateway.py:99-104`, `services/control-plane/src/cockpit/gateway.py:168-211`, `services/control-plane/src/cockpit/gateway.py:237-289`, `services/control-plane/src/cockpit/gateway.py:457-531`, `services/control-plane/src/cockpit/connectors/mcp.py:99-139`, `services/control-plane/src/cockpit/connectors/mcp.py:162-179`.
- Failure scenario: Workspace B refreshes the global MCP singleton with `mcp.shared.echo` as the trusted in-process read. Workspace A’s DB config defines that same tool ID as an untrusted remote stdio write. `find_tool()` and policy use B’s trusted/read/non-external manifest, but `_run_connector()` and `MCPConnector.execute()` use A’s DB config and invoke the remote write. Safe Mode therefore allows the mutation. Because the pre-dispatch durability check also consults the global manifest’s `external_side_effects=False`, a simulated process death after the remote effect leaves no durable `RUNNING` row; resume dispatches the effect a second time.
- Reproduction: 
  - `uv run pytest -q tests/test_adversarial_r3.py::test_r3_global_mcp_manifest_must_not_bypass_safe_mode`
  - `uv run pytest -q tests/test_adversarial_r3.py::test_r3_global_mcp_manifest_must_not_double_fire_after_crash`
  The first test records a remote mutation while Safe Mode is enabled. The second records the same non-idempotent effect twice across a simulated process death and resume.
- Impact: A dynamic connector tool can execute an unapproved external mutation in Safe Mode and silently double-fire after a crash. The decision, schema, risk, approval, idempotency, and execution config do not describe the same capability.
- Suggested fix: Resolve a workspace-specific immutable `ToolManifest` snapshot from that workspace’s connector config, and carry that exact object through validation, policy, durable intent, and execution. Never derive policy from a mutable global singleton for runtime-registered tools.
- Evidence: `test_adversarial_r3.py` tests named above; `r3_adversarial_tests.log` shows “DID NOT RAISE ToolDenied” and two recorded `non-idempotent-effect` entries.

### F3. Swapping a parent directory to a symlink after validation still writes outside configured roots — Critical — CONFIRMED
- Which fix / invariant / new surface it defeats: Round-1 F2 and Round-2 F3/ADR-015 filesystem containment; the claimed `O_NOFOLLOW` TOCTOU closure.
- Location: `services/control-plane/src/cockpit/connectors/local_files.py:160-182`, `services/control-plane/src/cockpit/connectors/local_files.py:192-218`, `services/control-plane/src/cockpit/connectors/base.py:202-233`.
- Failure scenario: `_resolve_write()` validates `root/notes/memo.md`. Before `os.open()`, another actor renames `root/notes` and replaces it with a symlink to an outside directory. `O_NOFOLLOW` protects only the final component (`memo.md`), not symlinks in parent components, so the write creates `outside/memo.md`.
- Reproduction: `uv run pytest -q tests/test_adversarial_r3.py::test_r3_parent_symlink_swap_must_not_escape_local_write`. The test performs the swap at the exact open boundary and confirms `outside/memo.md` contains the payload.
- Impact: A write approved for the vault can overwrite or create arbitrary files reachable through a raced parent symlink. Sync clients or another process touching a configured root can trigger the same class without controlling the cockpit process.
- Suggested fix: Walk from an already-open root directory descriptor using `openat`/`dir_fd` with `O_NOFOLLOW` on every component, then write via the verified descriptor. Pathname validation plus a final-component flag is not a complete containment primitive.
- Evidence: `test_adversarial_r3.py::test_r3_parent_symlink_swap_must_not_escape_local_write`; `r3_adversarial_tests.log` records “write followed a swapped parent symlink outside.”

### F4. Web connector configuration can redirect any process-environment secret to Firecrawl — Critical — CONFIRMED
- Which fix / invariant / new surface it defeats: The secret-store least-authority boundary and “secrets never leave through the wrong connector.”
- Location: `services/control-plane/src/cockpit/connectors/web.py:121-131`, `services/control-plane/src/cockpit/connectors/web.py:175-190`, `services/control-plane/src/cockpit/api/catalog.py:207-224`, `services/control-plane/src/cockpit/api/catalog.py:288-299`.
- Failure scenario: Patch the Web connector config to `{"search_provider":"firecrawl","api_key_env":"ANTHROPIC_API_KEY"}`. `_reject_secretlike()` examines only credential-shaped *values*, so the environment-variable name is accepted. The web connector then reads `ANTHROPIC_API_KEY` from the shared process environment and sends it as `Authorization: Bearer ...` to Firecrawl.
- Reproduction: 
  - Live API: `curl -X PATCH http://127.0.0.1:8787/api/v1/connectors/web -H 'content-type: application/json' -d '{"config":{"search_provider":"firecrawl","api_key_env":"ANTHROPIC_API_KEY"}}'` (accepted; captured in `r3_live_config_attack.log`).
  - Direct proof: `uv run pytest -q tests/test_adversarial_r3.py::test_r3_web_connector_must_not_read_arbitrary_environment_secret`; the captured outbound header is `Bearer sk-ant-EXFILTRATE1234567890`.
- Impact: Permission to configure one integration grants read/exfiltration access to every environment secret visible to the control-plane process, including model-provider and unrelated connector credentials.
- Suggested fix: Bind each connector to a fixed, code-defined secret identifier or a connector-scoped credential handle. Never accept an arbitrary environment variable name from mutable connector configuration.
- Evidence: `r3_live_config_attack.log`; `test_adversarial_r3.py::test_r3_web_connector_must_not_read_arbitrary_environment_secret`; `r3_adversarial_tests.log` shows the exact leaked Authorization value.

### F5. Basic-auth credentials in a fetch URL are persisted in tool calls, outputs, and events — Critical — CONFIRMED
- Which fix / invariant / new surface it defeats: The governing invariant that secrets never reach `tool_calls`, `run_events`, logs, artifacts, or API responses.
- Location: `services/control-plane/src/cockpit/connectors/web.py:221-264`, `services/control-plane/src/cockpit/gateway.py:291-318`, `services/control-plane/src/cockpit/gateway.py:543-558`, `services/control-plane/src/cockpit/logging.py:19-48`.
- Failure scenario: Call `web.fetch` with `http://alice:s3cr3t-password@93.184.216.34/private`. The SSRF parser allows the public host. Generic redaction does not recognize arbitrary URL userinfo passwords. The original input, returned `resp.url`, and human-readable completion summary all preserve the password.
- Reproduction: `uv run pytest -q tests/test_adversarial_r3.py::test_r3_basic_auth_url_secret_must_not_reach_toolcall_or_event`. It executes the real gateway path and then serializes the persisted `ToolCall.input`, `ToolCall.output`, and event payloads; all contain `s3cr3t-password`.
- Impact: A credential becomes durable in SQLite, backups, audit APIs, and the event stream. Anyone with local cockpit access can recover it long after the request.
- Suggested fix: Reject URLs containing userinfo, or strip credentials before validation/persistence and pass authentication through a secret handle. Add structured URL sanitization rather than relying only on credential-pattern regexes.
- Evidence: `test_adversarial_r3.py::test_r3_basic_auth_url_secret_must_not_reach_toolcall_or_event`; `r3_adversarial_tests.log` includes the complete unredacted persisted JSON.

### F6. The event sequence conflict retry crashes on its first real uniqueness conflict — High — CONFIRMED
- Which fix / invariant / new surface it defeats: Round-2 F12/ADR-015’s `UNIQUE(run_id, seq)` plus savepoint-retry guarantee.
- Location: `services/control-plane/src/cockpit/events.py:130-163`.
- Failure scenario: Two emitters select the same next sequence. One commits first; the second hits the unique constraint inside `begin_nested()`. SQLAlchemy has already removed/rolled back the candidate instance, but the handler calls `session.expunge(candidate)`, which raises `InvalidRequestError` before the loop can retry.
- Reproduction: 
  - `uv run pytest -q tests/test_adversarial_r3.py::test_r3_event_retry_must_survive_one_unique_conflict`
  - `cd services/control-plane && uv run python /mnt/data/probe_real_event_race.py`
  The real two-session probe prints `second error InvalidRequestError Instance <RunEvent ...> is not present in this Session`; only the first event remains.
- Impact: Concurrent scheduler/worker/provider events can crash a run or lose audit events precisely when the DB backstop detects a race.
- Suggested fix: Do not expunge an object that the savepoint rollback has already detached. Create a fresh candidate after rollback, explicitly expire/rollback the nested state as required, and test with two independent sessions emitting the same run concurrently.
- Evidence: `test_adversarial_r3.py::test_r3_event_retry_must_survive_one_unique_conflict`; `r3_real_event_race.log`; `r3_adversarial_tests.log` stack trace at `events.py:160`.

### F7. EventBus still publishes uncommitted events that disappear on rollback — High — CONFIRMED
- Which fix / invariant / new surface it defeats: ADR-012’s persistence-first/source-of-truth contract and Round-2 F9’s ghost-event fix.
- Location: `services/control-plane/src/cockpit/events.py:153-169`.
- Failure scenario: `emit()` flushes inside a savepoint, immediately calls `_publish()`, and returns while the caller still owns the outer transaction. A subscriber receives the event. The caller then rolls back; the database contains no corresponding row.
- Reproduction: `uv run pytest -q tests/test_adversarial_r3.py::test_r3_event_must_not_publish_before_outer_transaction_commits`. The queue contains an `artifact.created` event while a subsequent DB count is zero.
- Impact: UI state can show approvals, artifacts, completion, or failures that never committed. Reused/gapped autoincrement IDs can also poison `Last-Event-ID` handling and make a later real event appear already delivered.
- Suggested fix: Publish through a transactional outbox or an after-commit hook. `emit()` should persist only; fan-out must occur only after the outer transaction successfully commits.
- Evidence: `test_adversarial_r3.py::test_r3_event_must_not_publish_before_outer_transaction_commits`; `r3_adversarial_tests.log` includes the delivered-but-rolled-back event dictionary.

### F8. Approving a proposed memory before resume causes the replay to insert a duplicate — High — CONFIRMED
- Which fix / invariant / new surface it defeats: Round-2 F10/ADR-015 idempotent result persistence across crash/resume.
- Location: `services/control-plane/src/cockpit/worker.py:234-248`, `services/control-plane/src/cockpit/worker.py:279-321`.
- Failure scenario: `_persist_result()` commits a proposed memory. The process dies before verification; while the run is interrupted, the user approves that memory (`status=active`). Resume re-executes result persistence. The cleanup deletes only still-`proposed` memories, deliberately leaves the active row, and inserts the same proposal again as a new proposed row.
- Reproduction: `uv run pytest -q tests/test_adversarial_r3.py::test_r3_approved_memory_must_not_be_duplicated_on_result_replay`. Final rows are `[('active', 'remember this'), ('proposed', 'remember this')]`.
- Impact: One logical memory appears twice, can generate duplicate commitments or downstream actions, and presents the user with a second approval for a fact already approved.
- Suggested fix: Give each proposal a deterministic logical key scoped to the run and upsert it regardless of review status. A replay must reference the existing approved/rejected row rather than create a replacement proposal.
- Evidence: `test_adversarial_r3.py::test_r3_approved_memory_must_not_be_duplicated_on_result_replay`; `r3_adversarial_tests.log` lists both rows.

### F9. “Source-backed” memos accept fabricated citation indices without validation — High — CONFIRMED
- Which fix / invariant / new surface it defeats: ADR-016 citation integrity and the claim that facts in a source-backed Research Run are grounded in fetched sources.
- Location: `services/control-plane/src/cockpit/skills/research_run.py:102-129`, `services/control-plane/src/cockpit/skills/research_run.py:131-157`, `skills/research-run/manifest.yaml:16-17`.
- Failure scenario: Fetched attacker text is placed verbatim in the model prompt. The model response is accepted verbatim; there is no parser checking required sections, factual-claim citations, or whether each `[n]` is within `1..len(sources)`. A simulated injected response citing `[999]` is emitted as a successful `source_backed` memo with `source_count=1` and no unresolved issue. The only verification rule checks that a Markdown artifact exists.
- Reproduction: `uv run pytest -q tests/test_adversarial_r3.py::test_r3_source_backed_memo_must_reject_out_of_range_citations`. The malicious source instruction reaches the generator, `[999]` survives in the artifact, and `result.unresolved` is empty.
- Impact: A hostile page can launder unsupported claims into the “Facts” section and fabricate the appearance of grounding. The result is materially misleading even though its metadata says source-backed.
- Suggested fix: Parse and validate the memo deterministically: reject or downgrade out-of-range citations, require citations on each factual bullet, and surface validation failures. Prefer an evidence/claim intermediate schema over free-form Markdown generation.
- Evidence: `test_adversarial_r3.py::test_r3_source_backed_memo_must_reject_out_of_range_citations`; `r3_adversarial_tests.log` shows the accepted `[999]` beside the sole `[1]` source.

### F10. Approval editing persists a redacted value and then executes that altered value as though approved — High — CONFIRMED
- Which fix / invariant / new surface it defeats: Round-2 F5’s edited-input secret fix, edited-input correctness, and “no false success.”
- Location: `services/control-plane/src/cockpit/api/approvals.py:91-100`, `services/control-plane/src/cockpit/gateway.py:364-375`.
- Failure scenario: The user approves an edited `local_files.write` input whose content is `Bearer ABCDEFGHIJKLMNOPQRSTUVWXYZ`. The resolve endpoint applies `redact()` and stores `•••redacted•••` in `ToolCall.edited_input`. On resume the gateway treats that audit-safe copy as the executable source of truth and writes the mask to disk, then reports success.
- Reproduction: `uv run pytest -q tests/test_adversarial_r3.py::test_r3_approval_edit_must_not_silently_execute_redacted_input`. The resulting file contains `•••redacted•••`, not the approved content.
- Impact: Normal payloads that happen to resemble credentials are silently corrupted. More importantly, the approval preview and the actual effect diverge while the run can still complete successfully.
- Suggested fix: Separate executable input from its redacted audit representation. Reject inline secrets and require secret references, or store the executable value in an ephemeral/encrypted secret handle; never execute the redacted display copy.
- Evidence: `test_adversarial_r3.py::test_r3_approval_edit_must_not_silently_execute_redacted_input`; `r3_adversarial_tests.log` shows the exact expected and actual contents.

### F11. Migration 0003 cannot upgrade a legacy database containing duplicate event sequences — High — CONFIRMED
- Which fix / invariant / new surface it defeats: Round-2 F12’s migration/backstop and the required old-DB upgrade path.
- Location: `services/control-plane/alembic/versions/0003_memory_run_id_event_seq_unique.py:44-55`.
- Failure scenario: An old revision-0002 database contains two `run_events` rows with the same `(run_id, seq)`, which is exactly the state the pre-fix race could produce. Migration 0003 directly creates the unique index without first detecting or reconciling duplicates. SQLite raises `UNIQUE constraint failed`, leaving the application unable to upgrade/start.
- Reproduction: `uv run pytest -q tests/test_adversarial_r3.py::test_r3_migration_0003_must_reconcile_legacy_duplicate_event_sequences`. The test constructs a revision-0002 DB with duplicate sequence rows and runs the actual Alembic command; it exits 1 at `CREATE UNIQUE INDEX`.
- Impact: Users most affected by the old event race can be locked out by the migration intended to fix it. Manual database surgery is required before the new version boots.
- Suggested fix: Add a deterministic data-repair step before index creation—renumber duplicates in stable ID order or quarantine them with an explicit migration audit—then create and verify the unique index.
- Evidence: `test_adversarial_r3.py::test_r3_migration_0003_must_reconcile_legacy_duplicate_event_sequences`; full Alembic stack trace in `r3_adversarial_tests.log`.

### F12. Fetch limits apply after full buffering, and malformed HTML causes quadratic event-loop blocking — Medium — CONFIRMED
- Which fix / invariant / new surface it defeats: ADR-016 fetch safety and run-budget/availability expectations.
- Location: `services/control-plane/src/cockpit/connectors/web.py:96-111`, `services/control-plane/src/cockpit/connectors/web.py:221-254`.
- Failure scenario: `client.get()` downloads and decompresses the full response before `resp.content[:max_bytes]` is applied. A test server transmitted all 8,388,608 bytes despite the configured 1,500,000-byte cap. Separately, the regex that removes `<script>...</script>` repeatedly scans the remaining string when tags are unclosed: 8 KB took 0.025 s, 40 KB 0.697 s, 80 KB 2.54 s, and 160 KB 10.35 s. Parsing is synchronous on the main event loop, so an async timeout cannot interrupt it.
- Reproduction:
  - `uv run pytest -q tests/test_adversarial_r3.py::test_r3_web_fetch_must_stream_cap_instead_of_buffering_entire_body`
  - `uv run pytest -q tests/test_adversarial_r3.py::test_r3_html_reducer_must_not_have_quadratic_unclosed_script_redos`
- Impact: One malicious public page can consume unbounded response memory/bandwidth up to HTTPX’s timeout and then freeze the entire control-plane event loop; Research Run fetches up to three such pages.
- Suggested fix: Stream the response with a hard byte counter and abort before exceeding the limit, including decompressed bytes. Replace regex HTML parsing with a bounded parser and run CPU-heavy extraction in a worker thread/process with explicit input/time limits.
- Evidence: the two tests above; `r3_html_redos_benchmark.log`; `r3_adversarial_tests.log` reports 8 MB transferred and a 1.5-second timeout on roughly 240 KB of malformed HTML.

### F13. The multi-process claim check treats a cleared or foreign post-queue claim as owned — Medium — CONFIRMED
- Which fix / invariant / new surface it defeats: Round-2 F11’s claim-ownership recheck and ADR-004’s stated multi-process scaling path.
- Location: `services/control-plane/src/cockpit/worker.py:685-697`, `services/control-plane/src/cockpit/worker.py:736-770`, `services/control-plane/src/cockpit/worker.py:784-795`.
- Failure scenario: Process A claims a queued run. Process B starts and the blanket recovery update clears all queued claims. A’s queued task sees `worker_claim=None`, which `claim_still_owned()` treats as valid, and proceeds. B can claim the same row. Once A transitions it beyond queued, B’s task also passes because the predicate ignores claim ownership for non-queued statuses.
- Reproduction: `uv run pytest -q tests/test_adversarial_r3.py::test_r3_worker_task_must_require_exact_claim_ownership`; the predicate returns `True` for a queued run whose claim has been cleared. The complete interleaving follows directly through `recover_interrupted_runs()`, `claim_next_run()`, and `run_one()` at the locations above.
- Impact: Starting a second worker process can double-run the pipeline and, for effects not otherwise protected, duplicate external actions. The current launcher is single-process, so this is load/deployment dependent rather than an immediate default-path exploit.
- Suggested fix: Require an exact owner/lease token in every processing transition, reclaim only expired heartbeats, and atomically transition `queued → triaging` with the ownership predicate. Until then, explicitly reject multi-process startup.
- Evidence: `test_adversarial_r3.py::test_r3_worker_task_must_require_exact_claim_ownership`; `r3_adversarial_tests.log` shows `claim_still_owned(..., worker_claim=None)` returning true.

- Low severity: no Low findings; I did not pad the review with documentation or style observations.

## Fixes/boundaries I tried hard to break but couldn't
- SSRF literal/redirect handling: I tested loopback, metadata, RFC1918, decimal IPv4 (`2130706433`), hexadecimal/octal/short IPv4 forms, IPv4-mapped IPv6, NAT64 prefixes, unique-local IPv6, unspecified addresses, non-HTTP schemes, and userinfo host confusion. All were rejected; a literal public address was allowed. The manual redirect loop also revalidates every normal hop. DNS rebinding is the demonstrated remaining break.
- Research Run action boundary: fetched source text reaches the synthesis prompt, but the synthesis call itself receives no tools and the skill’s manifest allows only `web.search` and `web.fetch`. I did not find a path for source text to change deterministic policy or directly authorize a write in the same run. I did not have an Anthropic key to measure a live Claude model’s prompt-injection susceptibility; the confirmed defect is deterministic acceptance of invalid citations after generation.
- Round-1 F1 ordinary external-write path: when policy and execution use the same manifest, `_execute()` commits `RUNNING` before a non-idempotent external dispatch and resume refuses an ambiguous `RUNNING` row. Edited input is selected before `_execute()`. The demonstrated bypass requires the dynamic global/workspace manifest split in F2.
- Round-1/Round-2 filesystem fixes: static final-component symlinks, hardlinks, absolute/`..` Obsidian paths, unsafe globs, and already-present symlinked discovery entries were rejected by the author tests and my direct probes. The remaining escape requires racing a parent component after validation (F3).
- Round-1 F3 single-process claiming: sequential CAS claims and ordinary FSM requeue clearing held under the default single-process worker. F13 is specifically the still-advertised multi-process path.
- Round-1 F4 chat starvation: live chat no longer polls for approval and returns promptly. Read-only preflight avoids the exact chat rollback ghost-event path. General pre-commit event publication remains broken independently (F7).
- Round-1 F5 SSE backfill: pagination beyond 500 and high-water deduplication held under static and author tests. I did not reproduce the original backfill omission/duplication. Uncommitted live events can still corrupt the client’s observed stream, as reported separately.
- Round-1 F6 ordinary event-bus eviction: unsubscribe removes empty run subscriber sets, and the database now enforces `(run_id, seq)` uniqueness. The backstop catches duplicates; the new retry path fails to recover from the conflict (F6).
- ADR-014 preview separation: the gateway routes dry runs to `preview()` rather than `execute(dry_run=True)`, and n8n preview is now a local description with no HTTP request. A connector without a preview fails closed. I found no `python -O` route from the gateway to a real executor during a dry run.
- ADR-014 untrusted tools in the normal case: runtime n8n/MCP tools are untrusted, external, and approval-gated; Safe Mode beats allow rules when policy resolves the correct workspace manifest. F2 depends on policy resolving a different global manifest than execution.
- Round-2 F5 standard redaction paths: credential-shaped values in normal dictionaries and preview error strings are masked. The new failures are structured URL userinfo and executing the redacted approval copy, not a regression in those exact regex-covered cases.
- Round-2 F6 n8n idempotency: distinct payloads now produce distinct webhook keys, and identical payloads produce stable keys. I did not reproduce the prior preview/execute collision after n8n preview became local.
- Round-2 F7 Obsidian scope: ordinary absolute and `..` note paths are rejected and delegation uses the vault as the only root.
- Round-2 F8 execution configuration: n8n/MCP execution functions prefer `ExecutionContext.config`, so the request is routed to the run’s workspace rather than the singleton’s endpoint. The unresolved defect is that policy/schema/idempotency still come from the singleton (F2).
- Round-2 F10 proposed-state replay: replay replaces artifacts and still-proposed memories instead of duplicating them. The uncovered interleaving is a memory reviewed between crash and resume (F8).
- Migration normal paths: a fresh database migrated through 0001→0003 during `make setup`, and the unmodified suite passed. The failure requires legacy duplicate data that the prior race could have created (F11).

## New design concerns (not bugs)
- Safe Mode currently means “no external mutation,” not “no data leaves the machine.” `web.search` and `web.fetch` are trusted auto-running reads even though they disclose queries, URLs, IP address, and timing to external systems, and GET endpoints are not universally side-effect-free. Add a separate outbound-egress mode with domain/port allowlists and per-domain confirmation rather than overloading mutation risk.
- Source provenance should include the final validated URL, retrieval time, redirect chain, content hash, truncation status, and fetch mode. A Markdown list of URLs is insufficient evidence for later audit or reproducibility.
- Runtime-registered connector definitions need immutable, workspace-scoped versioning. Policy rules and approvals should bind to a manifest/config hash so changing a webhook/MCP definition invalidates prior trust and approval decisions.
- Advertise the worker as single-process until claims are leases with exact ownership and expiry. `workspace_id` and a CAS alone do not make the current in-process queue safe for horizontal scaling.

## Tests added
- `services/control-plane/tests/test_adversarial_r3.py` — 15 runnable attacks/assertions covering DNS rebinding, response buffering, HTML ReDoS, parent-symlink TOCTOU, workspace/global MCP classification divergence, Safe Mode bypass, crash double-fire, arbitrary environment-secret exfiltration, URL-credential persistence, event conflict recovery, pre-commit ghost events, reviewed-memory replay, citation forgery, approval-edit corruption, claim ownership, and legacy migration repair. Result against the reviewed branch: **15 failed** at the intended assertions; Ruff and Python compilation pass.
- `/mnt/data/probe_real_event_race.py` — real two-session event-sequence conflict; result: the second emitter raises `InvalidRequestError` instead of retrying.
- Baseline evidence: `140 passed` with `test_adversarial_r3.py` excluded; the author’s four review/web test files passed `53 passed`; Vitest `6 passed`; Ruff, Mypy, TypeScript, and ESLint passed.
- Runtime logs/evidence included with the review bundle: setup/migration, demo seed, health/web smoke, baseline and adversarial pytest, SSRF encoding matrix, HTML timing benchmark, live connector-config attack, real event race, and Playwright environment failure.
