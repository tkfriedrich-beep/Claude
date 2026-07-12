# INTEGRATION_CONTRACTS.md

The web/control-plane contract is **OpenAPI** (served at `/api/v1/openapi.json`, exported to
`packages/contracts/openapi.json`, TypeScript types generated to
`packages/contracts/src/api.d.ts` via `make contracts`). The UI must not call anything else.

## API surface (`/api/v1`)

| Area | Endpoints |
| --- | --- |
| Health | `GET /health`, `GET /doctor` |
| Onboarding | `GET /onboarding/status`, `POST /onboarding` |
| Commands | `POST /commands` (text, skill_id?, domain?, context_pack_id?, mode, budget_usd?, session_id?) |
| Sessions | `POST /sessions`, `GET /sessions`, `GET /sessions/{id}`, `POST /sessions/{id}/interrupt` |
| Runs | `GET /runs`, `GET /runs/{id}`, `POST /runs/{id}/cancel`, `POST /runs/{id}/interrupt`, `POST /runs/{id}/resume`, `GET /runs/{id}/events` |
| Events | `GET /events/stream?run_id=&since=` (SSE; also honors `Last-Event-ID`) |
| Approvals | `GET /approvals?status=`, `POST /approvals/{id}/resolve` (approve/deny, note, edited_input?, confirm_phrase?) |
| Skills | `GET /skills`, `GET /skills/{id}`, `POST /skills/{id}/run`, `PATCH /skills/{id}` (autonomy/enabled) |
| Connectors | `GET /connectors`, `GET /connectors/{id}`, `POST /connectors/{id}/health`, `PATCH /connectors/{id}`, `POST /connectors` (mcp/n8n registration) |
| Automations | `GET /automations`, `POST /automations`, `PATCH /automations/{id}`, `POST /automations/{id}/run-now?shadow=` |
| Artifacts | `GET /artifacts?run_id=`, `GET /artifacts/{id}`, `GET /artifacts/{id}/download` |
| Memories | `GET /memories?status=`, `PATCH /memories/{id}`, `DELETE /memories/{id}`, `GET /memories/export` |
| Cockpit data | `GET /briefing`, `GET /agenda`, `GET /projects`, `GET /people`, `GET /knowledge/search?q=`, `POST /knowledge/reindex` |
| Settings | `GET /settings`, `PATCH /settings` (safe_mode, kill_switch, theme, budgets, domains, autonomy defaults) |
| Policies | `GET /policies`, `POST /policies`, `PATCH /policies/{id}`, `DELETE /policies/{id}` |
| Usage | `GET /usage` |

Errors are RFC-9457 problem responses: `{type, title, status, detail, correlation_id}`.
Correlation IDs: browser sends `X-Correlation-Id` (generated per interaction); the control
plane propagates it through worker, gateway, connector calls, and logs, and returns it on
responses and problem bodies.

## SSE event envelope

```
id: <event id>            # ULID-ish, monotonic per stream
event: <event type>       # e.g. tool.completed
data: {"id","run_id","seq","type","ts","human_text","payload"}
```

Types (normalized; provider-specific events never reach the UI):
`run.queued run.started agent.status_changed assistant.message_delta plan.created
tool.proposed approval.required approval.resolved tool.started tool.progress tool.completed
tool.failed artifact.created verification.completed memory.proposed run.completed run.failed
run.cancelled`.

## Connector contract (Python protocol)

```python
class Connector(Protocol):
    id: str
    def get_manifest(self) -> ConnectorManifest          # from connectors/<id>/manifest.yaml
    async def health_check(self) -> HealthStatus         # ok | degraded | unavailable(+reason)
    def list_tools(self) -> list[ToolManifest]
    async def execute(self, tool_id: str, validated_input: dict,
                      ctx: ExecutionContext) -> ToolResult
    def normalize_result(self, raw: Any) -> dict         # → output schema
    def redact_for_log(self, data: dict) -> dict         # strip secrets/PII before logging
```

`ConnectorManifest`: id, name, version, category, auth_type, capabilities, required_scopes,
data_sensitivity, tools, mode (read_only/read_write), health, last_success_at.

`ToolManifest`: id, version, connector_id, capability, input_schema, output_schema,
access (read/write/destructive), sensitivity, scopes, external_side_effects, supports_dry_run,
idempotent, timeout_seconds, retry (max_attempts/backoff), approval (auto/required/forbidden),
undo_strategy.

Execution rules enforced by the gateway (not by connectors): schema-validate input and output;
apply policy before execute; timeouts + bounded retries (never retry non-idempotent external
writes after an ambiguous failure); idempotency key on every external mutation; record
confirmation result; redact before logging.

## Skill manifest (`skills/<id>/manifest.yaml`)

`id, name, description, version, domains[], risk_level, default_autonomy,
required_connectors[], allowed_tools[], input_schema, output_schema, supports_schedule,
supports_dry_run, timeout_seconds, max_steps, verification_rules[]` — plus `SKILL.md`,
`prompts/*.md` (versioned prompt assets), `fixtures/`, and schema files. The registry refuses
skills whose allowed_tools reference unknown tools.

## n8n connector

Registered per-webhook: name, url, HMAC secret ref (env name, never the value), input/output
JSON Schemas, timeout, retry, `supports_dry_run`. Invocation: `POST url` with
`X-Cockpit-Signature: sha256=HMAC(body)`, `X-Cockpit-Idempotency-Key`, `X-Correlation-Id`, and
`{"dry_run": bool, "payload": …}`. Response must match the registered output schema; anything
else is a schema-mismatch failure. Always labeled **external action** in previews (R3+).

## MCP registry

Users register trusted servers (stdio command or HTTP URL + optional auth env ref). On
registration the control plane discovers tools, converts their JSON Schemas into ToolManifests
(default classification: external, R3 writes / R1 reads, approval required — an admin can
tighten/loosen per tool via policies), and namespaces ids `mcp.<server>.<tool>`. MCP output is
untrusted data: schema-validated, redacted, never interpreted as instructions.

## Provider contract

`AgentRuntime` (see ARCHITECTURE.md) with `provider_sessions` persistence. Claude adapter uses
the official Agent SDK; `can_use_tool` requests become approval records; approval resolution
resolves the SDK callback. Usage (tokens/cost) captured per turn when the SDK reports it.
