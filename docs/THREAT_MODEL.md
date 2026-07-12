# THREAT_MODEL.md

Scope: single-user, local-first MVP. Assets: the user's files (vault, bizideas), credentials
(env), run/memory history, and the integrity of external systems reachable through connectors.

## Trust boundaries

1. **UI ↔ control plane** — localhost HTTP; CORS locked to localhost origins; no auth in MVP
   (single user, loopback bind). Binding to non-loopback is explicitly unsupported.
2. **Control plane ↔ model provider** — outbound HTTPS via official SDK; prompts may contain
   selected local content (user-visible in run events).
3. **Control plane ↔ connectors/MCP/n8n** — everything returned is **untrusted data**.
4. **Retrieved content ↔ policy** — retrieved text can never alter policy, permissions,
   secrets, or approvals; policies are code, prompts are not control surfaces.

## Top risks & mitigations

| # | Threat | Mitigation |
| --- | --- | --- |
| 1 | Prompt injection via files/MCP/webhooks steering the agent into harmful tool use | Deterministic policy gateway outside the model; R3+ needs human approval with full preview; retrieved content treated as data; tool allowlists per skill; approval text shows exactly what will be sent |
| 2 | Injection attempts to exfiltrate secrets | Secrets only via `SecretStore` (env); never in DB/logs/events; redaction filter on logs and event payloads; connectors receive secret *references*, resolved at call time |
| 3 | Overreach of filesystem tools | Roots allowlist (`data/`, configured vault, configured bizideas); path canonicalization + containment check; **writes resolve the final target (symlink/`..` escape rejected — ADR-013 F2)**; writes are R2/R3 → draft/approval; no shell tool (ADR-011) |
| 4 | Duplicate/replayed external writes (crash, retry) | Idempotency keys on every mutation; ambiguous failures never auto-retry non-idempotent tools; **a non-idempotent external write's RUNNING intent is committed before dispatch, and a run left RUNNING mid-write is never auto-replayed on resume — it fails for human reconciliation (ADR-013 F1)** |
| 5 | Stale approval executing later | Approval TTL; resolution checks expiry + run state; expired → new approval required |
| 6 | Runaway agent loops / cost blowup | max_steps, timeouts, per-run + daily budgets enforced in worker; low local concurrency; kill switch halts the worker; **a live chat turn never blocks a worker slot on human approval (ADR-013 F4)** |
| 7 | Malicious/compromised MCP server or hostile registered webhook | Runtime-registered tools are **untrusted**: always external + approval-required, never auto-run on their own classification; loosening only via an explicit allow rule in the policy editor; Safe Mode denies them; schema validation both ways; per-tool deny rules; health/audit visibility (ADR-014) |
| 11 | A "dry-run" preview performing the real effect | Dry-run is a distinct `preview()` connector method, not a flag on `execute()`; a connector without a deliberate preview fails closed instead of executing (ADR-014) |
| 8 | Forged n8n callbacks / MITM on webhooks | HMAC-signed requests, HTTPS URLs recommended, response schema validation, timeouts |
| 9 | Sensitive-domain data exposure (health/money/identity) | Domains off by default, read-only first, separate enablement, higher sensitivity labels propagate to redaction |
| 10 | UI misrepresenting state ("false success") | UI renders only persisted normalized events; completion requires a confirming tool result; verification step recorded |

## Explicit non-mitigations (honest limitations)

- This is **not a hardened sandbox**: the control plane runs as your user; a malicious local
  process or a compromised dependency can do what you can do. Supply-chain review, OS
  sandboxing (Tauri/macOS App Sandbox), and keychain secrets are roadmap items.
- The Claude Agent SDK spawns the `claude` CLI, which has its own tool surface; we constrain it
  via allowed_tools, cwd pinning, and the can_use_tool approval bridge — constraining, not a
  guarantee against SDK/CLI bugs.
- No at-rest encryption of SQLite in the MVP (local single-user machine assumption). Documented
  backup = file copy; protect the disk with FileVault or equivalent.
- Microphone/voice: not implemented; the design reserves push-to-talk only. Never
  always-listening.
- Web fetch (`web.fetch`) SSRF guard resolves the host, refuses private/loopback/link-local/
  reserved/metadata addresses, re-validates every redirect hop, AND **pins the connection to the
  validated IP** (Host + TLS SNI preserved), so DNS rebinding between validation and connect can no
  longer reach a new internal address (ADR-017 F1). Fetched content is always treated as untrusted
  data.
- The worker is **single-process** in the MVP. Horizontal scaling needs a leased-claim protocol
  (owner token + heartbeat expiry + atomic `queued→triaging`); until then `claim_still_owned`
  requires exact ownership but a multi-process deployment is out of scope (ADR-004, ADR-017 F13).

## Security invariants (tested)

- Safe Mode ⇒ no R3/R4 execution (unit + e2e tested).
- Kill switch ⇒ worker executes nothing.
- Unapproved R3 proposal ⇒ run pauses in `awaiting_approval`; execution before approval is
  impossible (gateway raises).
- Tool not in manifest/allowlist ⇒ deny.
- Path outside configured roots ⇒ deny.
- Secrets never appear in `run_events`, logs, or API payloads (redaction test) — including the
  approval **edit** path and connector **preview-error** text (R2-F5).

### Hardened by the round-2 adversarial review (`docs/reviews/codex-findings-r2.md`, ADR-015)

Each item has a regression test in `tests/test_review_r2_fixes.py`.

- **Safe Mode is a hard gate that beats allow rules.** A user `allow` rule cannot re-enable a
  user-registered connector's external call while Safe Mode is on (R2-F1).
- **Previews are side-effect-free by construction.** `n8n.preview()` sends no HTTP; it returns a
  local description of the request. A mislabeled dry-run cannot fire a real effect (R2-F2, and
  ADR-014's `preview()` fail-closed default).
- **Filesystem containment holds against symlink *and* hardlink *and* discovery traversal.** Writes
  refuse `O_NOFOLLOW`-rejected opens and `st_nlink > 1` hardlinks (R2-F3); list/search/reindex
  reject `..`/absolute globs and skip symlinked or out-of-root entries (R2-F4); an Obsidian write
  stays inside the vault (R2-F7).
- **External mutations are keyed by their payload.** The n8n idempotency key covers a canonical
  serialization of the input, so two distinct calls in one run cannot collide into a silent cached
  no-op (R2-F6).
- **A run acts under its own workspace's config.** Connector config is threaded per-workspace
  through `ExecutionContext`, so a payload cannot route to another workspace's endpoint via the
  global singleton (R2-F8; dormant in the single-user MVP).
- **A denied chat tool leaves no trace.** A read-only policy preflight decides allow/deny with no
  ToolCall/Approval/event writes — no ghost SSE events to roll back (R2-F9).
- **Result and event persistence are idempotent across crash-resume.** Replay replaces a run's
  artifacts and still-proposed memories rather than duplicating them (R2-F10); `UNIQUE(run_id,
  seq)` + a savepoint-retry in `emit()` make a duplicate event sequence number impossible
  (R2-F12).

### Hardened by the round-3 adversarial review (`docs/reviews/codex-findings-r3.md`, ADR-017)

Regression tests in `tests/test_review_r3_fixes.py` (F10/F13 in `tests/test_review_r2_fixes.py`).

- **`web.fetch` pins the connection to the validated IP** (Host + SNI preserved) — DNS rebinding
  can no longer reach an internal address after the guard passes (R3-F1).
- **Policy, durability, and execution use the same per-workspace manifest.** A dynamic n8n/MCP tool
  is resolved from the workspace's own `Connector.config`, so it cannot be policy-checked as another
  workspace's "trusted read" while executing as a write — closing a Safe Mode bypass and a
  double-fire (R3-F2).
- **Filesystem writes descend with `O_NOFOLLOW` on every component**, rejecting a parent-directory
  symlink swapped in after validation (R3-F3), in addition to final-component symlinks/hardlinks.
- **Secrets can't leak through the web connector:** its API-key env var is fixed in code (no config
  redirect — R3-F4), URL userinfo is rejected and redacted (R3-F5).
- **Events publish only after the outer transaction commits** (transactional outbox), so a
  rolled-back event never reaches SSE (R3-F7), and the seq-conflict retry no longer crashes (R3-F6).
- **Research Run validates citations** — an out-of-range `[n]` from an injected page is flagged, not
  presented as grounded (R3-F9).
- **The approval edit executes the raw value** (credential-shaped edits are rejected, not masked and
  written — R3-F10). **Migration 0003 reconciles legacy duplicate event seqs** before the unique
  index (R3-F11). **Fetch is bounded** — streamed byte cap + linear HTML parser, no ReDoS (R3-F12).
