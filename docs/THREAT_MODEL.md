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
| 3 | Overreach of filesystem tools | Roots allowlist (`data/`, configured vault, configured bizideas); path canonicalization + containment check; writes are R2/R3 → draft/approval; no shell tool (ADR-011) |
| 4 | Duplicate/replayed external writes (crash, retry) | Idempotency keys on every mutation; ambiguous failures never auto-retry non-idempotent tools; resume replays from checkpoint without re-firing completed writes |
| 5 | Stale approval executing later | Approval TTL; resolution checks expiry + run state; expired → new approval required |
| 6 | Runaway agent loops / cost blowup | max_steps, timeouts, per-run + daily budgets enforced in worker; low local concurrency; kill switch halts the worker |
| 7 | Malicious/compromised MCP server | Explicit trust-on-registration; default approval-required classification; schema validation both ways; per-tool deny rules; health/audit visibility |
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

## Security invariants (tested)

- Safe Mode ⇒ no R3/R4 execution (unit + e2e tested).
- Kill switch ⇒ worker executes nothing.
- Unapproved R3 proposal ⇒ run pauses in `awaiting_approval`; execution before approval is
  impossible (gateway raises).
- Tool not in manifest/allowlist ⇒ deny.
- Path outside configured roots ⇒ deny.
- Secrets never appear in `run_events`, logs, or API payloads (redaction test).
