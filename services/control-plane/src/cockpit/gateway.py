"""Typed Tool Gateway.

Every tool invocation — from any skill or runtime — flows through call_tool():

  manifest lookup → input schema validation → deterministic policy → (approval pause)
  → execution with timeout/retries → output schema validation → confirmation recording

Idempotency: the ToolCall row is keyed by sha256(run, tool, canonical input). Resumed runs
re-invoke executors from the top; completed calls replay their recorded result instead of
re-executing, so external writes never silently fire twice (BUILD_BRIEF invariant 6/7).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from jsonschema import Draft202012Validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cockpit.config import Settings
from cockpit.connectors.base import (
    BaseConnector,
    ConnectorError,
    ExecutionContext,
    ToolManifest,
    ToolResult,
)
from cockpit.enums import (
    ApprovalStatus,
    Autonomy,
    ConnectorMode,
    EventType,
    PolicyKind,
    RiskLevel,
    ToolCallStatus,
)
from cockpit.events import EventBus
from cockpit.ids import new_id
from cockpit.logging import get_logger, redact
from cockpit.models import Approval, Connector, Domain, PolicyRule, Run, Skill, ToolCall
from cockpit.policy import Decision, Outcome, PolicyContext, Rule, ToolSpec, evaluate

log = get_logger("cockpit.gateway")


class ToolDenied(Exception):
    def __init__(self, reason: str, *, decision: Decision | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.decision = decision


class ApprovalPending(Exception):
    """Raised when a call needs human approval; the worker parks the run."""

    def __init__(self, approval_id: str, title: str) -> None:
        super().__init__(f"approval pending: {title}")
        self.approval_id = approval_id
        self.title = title


class SchemaViolation(Exception):
    pass


def idempotency_key(run_id: str, tool_id: str, tool_input: dict[str, Any]) -> str:
    canonical = json.dumps(tool_input, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(f"{run_id}|{tool_id}|{canonical}".encode()).hexdigest()[:40]


def _validate(schema: dict[str, Any], data: dict[str, Any], what: str) -> None:
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: e.path)
    if errors:
        first = errors[0]
        raise SchemaViolation(
            f"{what} schema violation at /{'/'.join(map(str, first.path))}: {first.message}"
        )


class ToolGateway:
    def __init__(
        self,
        settings: Settings,
        bus: EventBus,
        connectors: dict[str, BaseConnector],
    ) -> None:
        self.settings = settings
        self.bus = bus
        self.connectors = connectors

    def find_tool(self, tool_id: str) -> tuple[BaseConnector, ToolManifest]:
        for connector in self.connectors.values():
            tool = connector.get_tool(tool_id)
            if tool is not None:
                return connector, tool
        raise ToolDenied(f"Unknown tool “{tool_id}” — not in any connector manifest.")

    async def _policy_context(self, session: AsyncSession, run: Run) -> PolicyContext:
        from cockpit.workspace import get_workspace_settings  # avoid cycle

        ws = await get_workspace_settings(session, run.workspace_id)
        skill_allowlist: frozenset[str] = frozenset()
        autonomy = Autonomy.ACT_WITH_APPROVAL
        if run.skill_slug:
            skill = await session.scalar(
                select(Skill).where(
                    Skill.workspace_id == run.workspace_id, Skill.slug == run.skill_slug
                )
            )
            if skill is not None:
                autonomy = Autonomy(skill.autonomy)
                skill_allowlist = frozenset(skill.manifest.get("allowed_tools", []))
        else:
            # chat runs: conservative default — act-with-approval, no allowlist restriction
            autonomy = Autonomy.ACT_WITH_APPROVAL

        domain_enabled = True
        if run.domain_key:
            domain = await session.scalar(
                select(Domain).where(
                    Domain.workspace_id == run.workspace_id, Domain.key == run.domain_key
                )
            )
            domain_enabled = bool(domain and domain.enabled)

        rules_rows = (
            await session.scalars(
                select(PolicyRule).where(
                    PolicyRule.workspace_id == run.workspace_id,
                    PolicyRule.enabled == True,  # noqa: E712
                )
            )
        ).all()
        rules = tuple(
            Rule(
                kind=PolicyKind(r.kind),
                tool_id=r.tool_id,
                connector_slug=r.connector_slug,
                skill_slug=r.skill_slug,
                enabled=r.enabled,
            )
            for r in rules_rows
        )
        from cockpit.enums import ExecMode

        return PolicyContext(
            safe_mode=ws.safe_mode,
            kill_switch=ws.kill_switch,
            exec_mode=ExecMode(run.mode),
            shadow=run.shadow,
            autonomy=autonomy,
            skill_slug=run.skill_slug,
            skill_allowlist=skill_allowlist,
            domain_enabled=domain_enabled,
            connector_enabled=True,  # refined below per connector row
            connector_mode=ConnectorMode.READ_WRITE,
            rules=rules,
        )

    async def call_tool(
        self,
        session: AsyncSession,
        run: Run,
        tool_id: str,
        tool_input: dict[str, Any],
        *,
        purpose: str,
        why: str = "",
        preview: str | None = None,
    ) -> ToolResult:
        """The one entry point for tool execution. May raise ToolDenied / ApprovalPending."""
        connector, tool = self.find_tool(tool_id)
        connector_row = await session.scalar(
            select(Connector).where(
                Connector.workspace_id == run.workspace_id, Connector.slug == connector.slug
            )
        )
        _validate(tool.input_schema, tool_input, f"{tool_id} input")

        key = idempotency_key(run.id, tool_id, tool_input)
        existing = await session.scalar(
            select(ToolCall).where(
                ToolCall.workspace_id == run.workspace_id, ToolCall.idempotency_key == key
            )
        )

        # Replay of a finished call (resumed run): return the recorded result, never re-execute.
        if existing is not None and existing.status == ToolCallStatus.COMPLETED:
            return ToolResult(
                ok=True,
                data=existing.output or {},
                summary="(replayed from earlier execution)",
                external_confirmed=existing.external_confirmed,
            )
        if existing is not None and existing.status == ToolCallStatus.DENIED:
            raise ToolDenied(existing.error or "You denied this action.")

        # A call left RUNNING is one that was dispatched but never recorded completion —
        # i.e. the process died between the connector effect and the commit (F1). For a
        # non-idempotent external write the effect MAY have landed, so we must never
        # auto-replay it: mark it failed and make the human reconcile. (Idempotent/local
        # writes are safe to re-run and fall through.)
        if (
            existing is not None
            and existing.status == ToolCallStatus.RUNNING
            and tool.external_side_effects
            and not tool.idempotent
        ):
            existing.status = ToolCallStatus.FAILED.value
            existing.error = (
                "Interrupted after this action was dispatched — its external effect may "
                "already have happened. It was not retried automatically. Check the target "
                "system, then run it again explicitly if it did not complete."
            )
            await self.bus.emit(
                session,
                workspace_id=run.workspace_id,
                run_id=run.id,
                type=EventType.TOOL_FAILED,
                payload={
                    "tool_id": tool_id,
                    "reason": "interrupted after dispatch — not auto-retried",
                    "needs_reconciliation": True,
                },
            )
            raise ToolDenied(existing.error, decision=None)

        import dataclasses

        base_ctx = await self._policy_context(session, run)
        ctx = dataclasses.replace(
            base_ctx,
            connector_enabled=bool(connector_row and connector_row.enabled),
            connector_mode=ConnectorMode(connector_row.mode)
            if connector_row
            else ConnectorMode.READ_ONLY,
        )
        spec = ToolSpec(
            tool_id=tool.id,
            connector_slug=connector.slug,
            access=tool.access,
            risk_level=tool.risk_level,
            external_side_effects=tool.external_side_effects,
            supports_dry_run=tool.supports_dry_run,
            idempotent=tool.idempotent,
        )
        decision = evaluate(spec, ctx)
        # Manifest-level "approval: required" tightens (never loosens) the policy result.
        if (
            decision.outcome is Outcome.ALLOW
            and tool.approval == "required"
            and spec.access.value != "read"
            and not decision.forced_dry_run
        ):
            decision = Decision(
                Outcome.REQUIRE_APPROVAL,
                "This tool always requires your approval before writing.",
                decision.risk_level,
            )

        if existing is None:
            existing = ToolCall(
                id=new_id("tc"),
                workspace_id=run.workspace_id,
                run_id=run.id,
                tool_id=tool_id,
                connector_slug=connector.slug,
                status=ToolCallStatus.PROPOSED.value,
                risk_level=decision.risk_level.value,
                purpose=purpose,
                input=redact(tool_input),
                idempotency_key=key,
            )
            session.add(existing)
            await session.flush()
            await self.bus.emit(
                session,
                workspace_id=run.workspace_id,
                run_id=run.id,
                type=EventType.TOOL_PROPOSED,
                payload={
                    "tool_id": tool_id,
                    "tool_call_id": existing.id,
                    "purpose": purpose,
                    "risk": decision.risk_level.value,
                    "decision": decision.outcome.value,
                    "reason": decision.reason,
                },
            )

        if decision.outcome is Outcome.DENY:
            existing.status = ToolCallStatus.DENIED.value
            existing.error = decision.reason
            await self.bus.emit(
                session,
                workspace_id=run.workspace_id,
                run_id=run.id,
                type=EventType.TOOL_FAILED,
                payload={"tool_id": tool_id, "reason": decision.reason, "policy": True},
            )
            raise ToolDenied(decision.reason, decision=decision)

        if decision.outcome is Outcome.REQUIRE_APPROVAL:
            if existing.status == ToolCallStatus.APPROVED.value:
                pass  # resumed after approval — fall through to execution
            else:
                approval = await self._get_or_create_approval(
                    session,
                    run,
                    existing,
                    connector,
                    tool,
                    tool_input,
                    decision,
                    purpose=purpose,
                    why=why,
                    preview=preview,
                )
                if approval.status == ApprovalStatus.PENDING.value:
                    raise ApprovalPending(approval.id, approval.title)
                if approval.status in (
                    ApprovalStatus.DENIED.value,
                    ApprovalStatus.EXPIRED.value,
                    ApprovalStatus.CANCELLED.value,
                ):
                    existing.status = ToolCallStatus.DENIED.value
                    existing.error = f"Approval {approval.status}."
                    raise ToolDenied(
                        "You denied this action."
                        if approval.status == ApprovalStatus.DENIED.value
                        else f"The approval {approval.status} before it could run.",
                        decision=decision,
                    )
                # approved → execute

        if existing.edited_input is not None:
            tool_input = dict(existing.edited_input)
            _validate(tool.input_schema, tool_input, f"{tool_id} edited input")
        return await self._execute(
            session,
            run,
            connector,
            tool,
            existing,
            tool_input,
            dry_run=decision.forced_dry_run,
        )

    async def _get_or_create_approval(
        self,
        session: AsyncSession,
        run: Run,
        tool_call: ToolCall,
        connector: BaseConnector,
        tool: ToolManifest,
        tool_input: dict[str, Any],
        decision: Decision,
        *,
        purpose: str,
        why: str,
        preview: str | None,
    ) -> Approval:
        approval = await session.scalar(
            select(Approval).where(Approval.tool_call_id == tool_call.id)
        )
        if approval is not None:
            # Stale approvals cannot execute (THREAT_MODEL #5).
            if (
                approval.status == ApprovalStatus.PENDING.value
                and approval.expires_at
                and approval.expires_at < datetime.now(UTC)
            ):
                approval.status = ApprovalStatus.EXPIRED.value
                approval.resolved_at = datetime.now(UTC)
            return approval

        diff_preview = preview
        if diff_preview is None and tool.supports_dry_run:
            # Dry-run is side-effect free by contract: run it to show an honest preview.
            try:
                dry = await self._run_connector(connector, tool, tool_input, run, dry_run=True)
                diff_preview = dry.data.get("diff") or dry.summary or None
            except Exception as exc:  # preview failure must not block the approval card
                diff_preview = f"(preview unavailable: {exc})"

        approval = Approval(
            id=new_id("apr"),
            workspace_id=run.workspace_id,
            run_id=run.id,
            tool_call_id=tool_call.id,
            status=ApprovalStatus.PENDING.value,
            title=purpose or f"Use {tool.name or tool.id}",
            what=purpose or tool.description,
            why=why or f"Requested by {run.skill_slug or 'your command'}: {run.title}",
            target=f"{connector.get_manifest().name} ({connector.slug})",
            data_preview=redact(tool_input),
            diff_preview=diff_preview,
            risk_level=decision.risk_level.value,
            reversibility=tool.undo_strategy
            or (
                "Reversible"
                if tool.risk_level in (RiskLevel.R2, RiskLevel.R3)
                else "May not be reversible"
            ),
            confirm_phrase_required=decision.confirm_phrase_required,
            expires_at=datetime.now(UTC) + timedelta(hours=self.settings.approval_ttl_hours),
        )
        session.add(approval)
        await session.flush()
        await self.bus.emit(
            session,
            workspace_id=run.workspace_id,
            run_id=run.id,
            type=EventType.APPROVAL_REQUIRED,
            payload={
                "approval_id": approval.id,
                "title": approval.title,
                "tool_id": tool.id,
                "risk": approval.risk_level,
                "expires_at": approval.expires_at.isoformat() if approval.expires_at else None,
            },
        )
        return approval

    async def _run_connector(
        self,
        connector: BaseConnector,
        tool: ToolManifest,
        tool_input: dict[str, Any],
        run: Run,
        *,
        dry_run: bool,
    ) -> ToolResult:
        from cockpit.workspace import allowed_roots_for  # avoid cycle

        exec_ctx = ExecutionContext(
            workspace_id=run.workspace_id,
            run_id=run.id,
            correlation_id=run.correlation_id or "",
            dry_run=dry_run,
            roots=await allowed_roots_for(run.workspace_id),
            config=getattr(connector, "runtime_config", {}) or {},
            settings=self.settings,
        )
        return await asyncio.wait_for(
            connector.execute(tool.id, tool_input, exec_ctx), timeout=tool.timeout_seconds
        )

    async def _execute(
        self,
        session: AsyncSession,
        run: Run,
        connector: BaseConnector,
        tool: ToolManifest,
        tool_call: ToolCall,
        tool_input: dict[str, Any],
        *,
        dry_run: bool,
    ) -> ToolResult:
        tool_call.status = ToolCallStatus.RUNNING.value
        tool_call.dry_run = dry_run
        tool_call.started_at = datetime.now(UTC)
        await self.bus.emit(
            session,
            workspace_id=run.workspace_id,
            run_id=run.id,
            type=EventType.TOOL_STARTED,
            payload={"tool_id": tool.id, "purpose": tool_call.purpose, "dry_run": dry_run},
        )
        # Durably persist the RUNNING intent BEFORE dispatching a non-idempotent external
        # write, so a crash mid-call leaves a visible RUNNING row and resume refuses to
        # replay it (F1 — never double-fire an external effect).
        if tool.external_side_effects and not tool.idempotent and not dry_run:
            await session.commit()

        attempts = max(1, tool.retry.max_attempts)
        last_error: str | None = None
        t0 = time.monotonic()
        for attempt in range(1, attempts + 1):
            tool_call.attempt = attempt
            try:
                result = await self._run_connector(
                    connector, tool, tool_input, run, dry_run=dry_run
                )
                if result.ok:
                    _validate(tool.output_schema, result.data, f"{tool.id} output")
                    tool_call.status = ToolCallStatus.COMPLETED.value
                    tool_call.output = connector.redact_for_log(result.data)
                    tool_call.external_confirmed = result.external_confirmed
                    tool_call.finished_at = datetime.now(UTC)
                    tool_call.duration_ms = int((time.monotonic() - t0) * 1000)
                    run.steps += 1
                    await self.bus.emit(
                        session,
                        workspace_id=run.workspace_id,
                        run_id=run.id,
                        type=EventType.TOOL_COMPLETED,
                        payload={
                            "tool_id": tool.id,
                            "summary": result.summary,
                            "dry_run": dry_run,
                            "external_confirmed": result.external_confirmed,
                            "duration_ms": tool_call.duration_ms,
                        },
                    )
                    return result
                last_error = result.error or "tool reported failure"
            except TimeoutError:
                last_error = f"timed out after {tool.timeout_seconds}s"
            except SchemaViolation as exc:
                last_error = str(exc)
                break  # schema mismatch will not fix itself by retrying
            except ConnectorError as exc:
                last_error = str(exc)
            except Exception as exc:  # unexpected connector bug
                log.exception("connector crash in %s", tool.id)
                last_error = f"connector error: {exc}"

            # Never blind-retry a non-idempotent external write after an ambiguous failure:
            # the effect may have landed (THREAT_MODEL #4).
            if tool.external_side_effects and not tool.idempotent and not dry_run:
                last_error = (last_error or "") + " (not retried: external effect may have "
                "already occurred — check the target system)"
                break
            if attempt < attempts:
                await asyncio.sleep(tool.retry.backoff_seconds * attempt)

        tool_call.status = ToolCallStatus.FAILED.value
        tool_call.error = last_error
        tool_call.finished_at = datetime.now(UTC)
        tool_call.duration_ms = int((time.monotonic() - t0) * 1000)
        await self.bus.emit(
            session,
            workspace_id=run.workspace_id,
            run_id=run.id,
            type=EventType.TOOL_FAILED,
            payload={"tool_id": tool.id, "reason": last_error, "attempts": tool_call.attempt},
        )
        return ToolResult(ok=False, error=last_error)
