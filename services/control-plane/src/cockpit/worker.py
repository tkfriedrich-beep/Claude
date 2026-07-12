"""Run worker — claims queued runs and drives them through the pipeline:

  triage → route to one skill (or chat) → plan → policy/approvals (inside the gateway)
  → execute → verify → quality review → present/record

The runs table is the job queue (ADR-004): claiming uses an atomic UPDATE … WHERE status =
'queued'. On startup, stale in-flight runs are marked interrupted; awaiting_approval runs are
untouched and resume via re-queueing when their approval resolves.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from jsonschema import Draft202012Validator
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cockpit.config import Settings
from cockpit.enums import EventType, RunKind, RunStatus, SessionStatus
from cockpit.events import EventBus, get_bus
from cockpit.gateway import ApprovalPending, ToolDenied, ToolGateway
from cockpit.ids import new_id
from cockpit.logging import get_logger
from cockpit.models import (
    Artifact,
    Memory,
    MemorySource,
    ProviderSession,
    Run,
    UserProfile,
)
from cockpit.registry import Registry, get_registry
from cockpit.runtime import ProviderUnavailable, get_runtime
from cockpit.runtime.base import RuntimeEvent, SessionContext
from cockpit.runtime.claude import load_otto_prompt
from cockpit.skills import EXECUTORS
from cockpit.skills.base import RunCancelled, SkillContext, SkillFailure, SkillResult
from cockpit.state_machine import transition
from cockpit.workspace import allowed_roots_for, get_workspace_settings

log = get_logger("cockpit.worker")

WORKER_ID = new_id("wrk")

ROUTE_KEYWORDS: dict[str, list[str]] = {
    "project-pulse": ["project pulse", "project status", "projects update"],
    "morning-brief": ["morning brief", "briefing", "what matters"],
    "daily-plan": ["daily plan", "plan my day", "time block"],
    "decision-memo": ["decision memo", "decide between", "decision:"],
    "business-idea-triage": ["idea triage", "business idea", "triage ideas", "bizideas"],
    "weekly-review": ["weekly review", "review my week"],
    "commitment-sweep": ["commitment sweep", "find my promises", "follow-ups"],
    "research-run": ["research:", "research run"],
}


class RunProcessor:
    def __init__(self, settings: Settings, registry: Registry, bus: EventBus) -> None:
        self.settings = settings
        self.registry = registry
        self.bus = bus
        self.gateway = ToolGateway(settings, bus, registry.connectors)

    # ------------------------------------------------------------------ pipeline

    async def process(self, session: AsyncSession, run: Run) -> None:
        try:
            ws = await get_workspace_settings(session, run.workspace_id)
            if ws.kill_switch:
                await transition(
                    session,
                    self.bus,
                    run,
                    RunStatus.FAILED,
                    reason="Kill switch is engaged — execution halted.",
                )
                await session.commit()
                return

            if RunStatus(run.status) is RunStatus.QUEUED:
                await transition(session, self.bus, run, RunStatus.TRIAGING)
                await session.commit()

            # Budget gate (daily + per-run) before any real work.
            budget_error = await self._check_budgets(session, run, ws)
            if budget_error:
                await transition(session, self.bus, run, RunStatus.FAILED, reason=budget_error)
                await session.commit()
                return

            if run.kind == RunKind.CHAT.value:
                await self._process_chat(session, run, ws)
            else:
                await self._process_skill(session, run, ws)
        except Exception as exc:
            log.exception("run %s crashed", run.id)
            await session.rollback()
            fresh = await session.get(Run, run.id)
            if fresh is not None and RunStatus(fresh.status) not in (
                RunStatus.COMPLETED,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
                RunStatus.AWAITING_APPROVAL,
            ):
                try:
                    await transition(
                        session,
                        self.bus,
                        fresh,
                        RunStatus.FAILED,
                        reason=f"Unexpected error: {exc}",
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()

    # ------------------------------------------------------------------ skill runs

    async def _process_skill(self, session: AsyncSession, run: Run, ws: Any) -> None:
        resumed = bool(run.checkpoint.get("resumed_from_approval"))
        slug = run.skill_slug or self._route(run.command_text)
        if slug is None:
            # No skill matched — treat as chat.
            run.kind = RunKind.CHAT.value
            await session.commit()
            await self._process_chat(session, run, ws)
            return
        run.skill_slug = slug
        skill_def = self.registry.skills.get(slug)
        executor_cls = EXECUTORS.get(slug)
        if skill_def is None or executor_cls is None:
            await transition(
                session, self.bus, run, RunStatus.FAILED, reason=f"Skill “{slug}” is not installed."
            )
            await session.commit()
            return
        manifest = skill_def.manifest
        if not run.title or run.title == "Run":
            run.title = manifest.get("name", slug)

        # Validate skill input against its schema (empty input allowed if schema permits).
        input_schema = manifest.get("input_schema") or {"type": "object"}
        errors = sorted(
            Draft202012Validator(input_schema).iter_errors(run.input or {}),
            key=lambda e: e.path,
        )
        if errors:
            await transition(
                session,
                self.bus,
                run,
                RunStatus.FAILED,
                reason=f"Input invalid: {errors[0].message}",
            )
            await session.commit()
            return

        ctx = SkillContext(
            session=session,
            run=run,
            gateway=self.gateway,
            bus=self.bus,
            settings=self.settings,
            ws=ws,
            manifest=manifest,
            generate=self._make_generator(ws),
        )
        executor = executor_cls(ctx)

        try:
            if RunStatus(run.status) is RunStatus.TRIAGING:
                await transition(session, self.bus, run, RunStatus.PLANNING)
                plan = await executor.plan()
                run.plan = {
                    "steps": plan.steps,
                    "expected_tools": plan.expected_tools,
                    "side_effects_expected": plan.side_effects_expected,
                    "success_checks": plan.success_checks,
                    "assumption": plan.assumption,
                }
                await self.bus.emit(
                    session,
                    workspace_id=run.workspace_id,
                    run_id=run.id,
                    type=EventType.PLAN_CREATED,
                    payload=run.plan,
                )
                await session.commit()

            if RunStatus(run.status) in (RunStatus.PLANNING, RunStatus.AWAITING_APPROVAL):
                await transition(
                    session,
                    self.bus,
                    run,
                    RunStatus.EXECUTING,
                    reason="resumed after approval" if resumed else None,
                )
                await session.commit()

            timeout = int(manifest.get("timeout_seconds", self.settings.run_timeout_default))
            result = await asyncio.wait_for(executor.execute(), timeout=timeout)
        except ApprovalPending as pending:
            run.checkpoint = {"resumed_from_approval": pending.approval_id}
            await transition(session, self.bus, run, RunStatus.AWAITING_APPROVAL)
            await session.commit()
            return
        except RunCancelled:
            await session.commit()  # run is already cancelled; keep the event trail
            return
        except (SkillFailure, ToolDenied) as exc:
            await session.commit()  # keep tool-call/event trail
            await transition(session, self.bus, run, RunStatus.FAILED, reason=str(exc))
            await session.commit()
            return
        except TimeoutError:
            await transition(
                session,
                self.bus,
                run,
                RunStatus.FAILED,
                reason=f"Timed out after {manifest.get('timeout_seconds')}s.",
            )
            await session.commit()
            return

        await self._persist_result(session, run, result)
        await self._verify_and_review(session, run, manifest, result)

    async def _persist_result(self, session: AsyncSession, run: Run, result: SkillResult) -> None:
        artifacts_meta = []
        for spec in result.artifacts:
            artifact_dir = self.settings.artifacts_dir / run.id
            artifact_dir.mkdir(parents=True, exist_ok=True)
            path = artifact_dir / spec.filename
            path.write_text(spec.content, encoding="utf-8")
            row = Artifact(
                id=new_id("art"),
                workspace_id=run.workspace_id,
                run_id=run.id,
                skill_slug=run.skill_slug,
                kind=spec.kind,
                title=spec.title,
                path=f"{run.id}/{spec.filename}",
                mime=spec.mime,
                size_bytes=len(spec.content.encode()),
                meta={**spec.meta, "generation_mode": result.generation_mode},
            )
            session.add(row)
            await session.flush()
            artifacts_meta.append({"id": row.id, "title": row.title, "kind": row.kind})
            await self.bus.emit(
                session,
                workspace_id=run.workspace_id,
                run_id=run.id,
                type=EventType.ARTIFACT_CREATED,
                payload={"artifact_id": row.id, "title": row.title, "kind": row.kind},
            )

        for proposal in result.memory_proposals:
            memory = Memory(
                id=new_id("mem"),
                workspace_id=run.workspace_id,
                kind=proposal.kind,
                status="proposed",
                content=proposal.content,
                structured=proposal.structured,
                confidence=proposal.confidence,
                domain_key=proposal.domain_key,
                rationale=proposal.rationale,
            )
            session.add(memory)
            await session.flush()
            for src in proposal.sources:
                session.add(
                    MemorySource(
                        id=new_id("msr"),
                        workspace_id=run.workspace_id,
                        memory_id=memory.id,
                        source_type=src.get("source_type", "file"),
                        reference=src.get("reference", ""),
                        excerpt=src.get("excerpt", ""),
                    )
                )
            await self.bus.emit(
                session,
                workspace_id=run.workspace_id,
                run_id=run.id,
                type=EventType.MEMORY_PROPOSED,
                payload={"memory_id": memory.id, "summary": proposal.content[:100]},
            )

        run.result = {
            "summary_md": result.summary_md,
            "data": result.data,
            "sources": result.sources,
            "unresolved": result.unresolved,
            "artifacts": artifacts_meta,
            "generation_mode": result.generation_mode,
        }
        await session.commit()

    async def _verify_and_review(
        self, session: AsyncSession, run: Run, manifest: dict[str, Any], result: SkillResult
    ) -> None:
        await transition(session, self.bus, run, RunStatus.VERIFYING)
        checks = []
        for rule in manifest.get("verification_rules", []):
            checks.append(await self._verify_rule(session, run, manifest, result, rule))
        passed = all(c["passed"] for c in checks) if checks else True
        run.verification = {"passed": passed, "checks": checks}
        await self.bus.emit(
            session,
            workspace_id=run.workspace_id,
            run_id=run.id,
            type=EventType.VERIFICATION_COMPLETED,
            payload={"passed": passed, "checks": checks},
        )
        await session.commit()
        if not passed:
            await transition(
                session,
                self.bus,
                run,
                RunStatus.FAILED,
                reason="Verification failed: "
                + "; ".join(c["rule"] for c in checks if not c["passed"]),
            )
            await session.commit()
            return

        await transition(session, self.bus, run, RunStatus.REVIEWING)
        review_notes = []
        if not result.summary_md.strip():
            review_notes.append("Result summary is empty.")
        if result.unresolved:
            review_notes.append(f"{len(result.unresolved)} unresolved item(s) surfaced.")
        run.review = {"passed": not any("empty" in n for n in review_notes), "notes": review_notes}
        await session.commit()
        await transition(session, self.bus, run, RunStatus.COMPLETED)
        await session.commit()

    async def _verify_rule(
        self,
        session: AsyncSession,
        run: Run,
        manifest: dict[str, Any],
        result: SkillResult,
        rule: str,
    ) -> dict[str, Any]:
        try:
            if rule.startswith("artifact_exists"):
                kind = rule.split(":", 1)[1] if ":" in rule else None
                artifacts = (
                    await session.scalars(select(Artifact).where(Artifact.run_id == run.id))
                ).all()
                ok = any(a.kind == kind for a in artifacts) if kind else bool(artifacts)
                return {
                    "rule": rule,
                    "passed": ok,
                    "detail": f"{len(artifacts)} artifact(s) recorded",
                }
            if rule == "sources_nonempty":
                return {
                    "rule": rule,
                    "passed": bool(result.sources),
                    "detail": f"{len(result.sources)} source(s)",
                }
            if rule == "output_schema_valid":
                schema = manifest.get("output_schema") or {"type": "object"}
                errs = list(Draft202012Validator(schema).iter_errors(result.data))
                return {
                    "rule": rule,
                    "passed": not errs,
                    "detail": errs[0].message if errs else "valid",
                }
            if rule == "no_unconfirmed_success":
                from cockpit.models import ToolCall

                calls = (
                    await session.scalars(
                        select(ToolCall).where(
                            ToolCall.run_id == run.id, ToolCall.status == "completed"
                        )
                    )
                ).all()
                bad = [
                    c.tool_id
                    for c in calls
                    if c.output is not None
                    and not c.dry_run
                    and self._tool_has_side_effects(c.tool_id)
                    and not c.external_confirmed
                ]
                return {
                    "rule": rule,
                    "passed": not bad,
                    "detail": "all external effects confirmed"
                    if not bad
                    else f"unconfirmed: {bad}",
                }
            return {"rule": rule, "passed": True, "detail": "unknown rule — skipped"}
        except Exception as exc:
            return {"rule": rule, "passed": False, "detail": f"verifier crashed: {exc}"}

    def _tool_has_side_effects(self, tool_id: str) -> bool:
        try:
            _, tool = self.gateway.find_tool(tool_id)
            return tool.external_side_effects
        except Exception:
            return False

    # ------------------------------------------------------------------ chat runs

    async def _process_chat(self, session: AsyncSession, run: Run, ws: Any) -> None:
        provider = ws.provider
        runtime = get_runtime(provider)
        available, detail = runtime.available()
        if not available:
            runtime = get_runtime("mock")
            await self.bus.emit(
                session,
                workspace_id=run.workspace_id,
                run_id=run.id,
                type=EventType.TOOL_PROGRESS,
                payload={
                    "message": f"Provider “{provider}” unavailable ({detail}) — "
                    "using the offline demo runtime."
                },
            )
            provider = "mock"
        run.provider = provider

        profile = await session.scalar(
            select(UserProfile).where(UserProfile.workspace_id == run.workspace_id)
        )
        assistant_name = profile.assistant_name if profile else "Otto"
        user_name = profile.user_name if profile else "there"

        ps: ProviderSession | None = None
        if run.session_id:
            ps = await session.get(ProviderSession, run.session_id)
        if ps is None:
            ps = ProviderSession(
                id=new_id("ses"),
                workspace_id=run.workspace_id,
                provider=provider,
                status=SessionStatus.ACTIVE.value,
                title=(run.command_text or "New session")[:80],
            )
            session.add(ps)
            await session.flush()
            run.session_id = ps.id

        sctx = SessionContext(
            workspace_id=run.workspace_id,
            internal_session_id=ps.id,
            external_session_id=ps.external_session_id,
            system_prompt=load_otto_prompt(
                "otto_v1", assistant_name=assistant_name, user_name=user_name
            ),
            workspace_roots=await allowed_roots_for(run.workspace_id),
            assistant_name=assistant_name,
            settings={"max_turns": 8},
        )

        if RunStatus(run.status) is RunStatus.TRIAGING:
            await transition(session, self.bus, run, RunStatus.PLANNING)
            run.plan = {
                "steps": [f"Respond via {provider} runtime"],
                "expected_tools": [],
                "side_effects_expected": False,
                "success_checks": [],
            }
            await self.bus.emit(
                session,
                workspace_id=run.workspace_id,
                run_id=run.id,
                type=EventType.PLAN_CREATED,
                payload=run.plan,
            )
            await transition(session, self.bus, run, RunStatus.EXECUTING)
            await session.commit()

        try:
            if ps.external_session_id:
                await runtime.resume_session(sctx)
            else:
                await runtime.start_session(sctx)
        except ProviderUnavailable as exc:
            await transition(session, self.bus, run, RunStatus.FAILED, reason=str(exc))
            await session.commit()
            return

        async def on_event(event: RuntimeEvent) -> None:
            await self.bus.emit(
                session,
                workspace_id=run.workspace_id,
                run_id=run.id,
                type=event.type,
                payload=event.payload,
                human_text=event.human_text,
            )
            await session.commit()

        async def can_use_tool(
            tool_name: str, tool_input: dict[str, Any]
        ) -> tuple[bool, str, dict[str, Any]]:
            return await self._chat_permission(session, run, tool_name, tool_input)

        try:
            turn = await runtime.run_turn(sctx, run.command_text, on_event, can_use_tool)
        except ProviderUnavailable as exc:
            await transition(session, self.bus, run, RunStatus.FAILED, reason=str(exc))
            await session.commit()
            return
        finally:
            ps.external_session_id = sctx.external_session_id
            ps.last_active_at = datetime.now(UTC)
            await session.commit()

        run.tokens_in += turn.usage.tokens_in
        run.tokens_out += turn.usage.tokens_out
        run.cost_usd += turn.usage.cost_usd
        run.result = {
            "summary_md": turn.final_text,
            "data": {"stop_reason": turn.stop_reason},
            "sources": [],
            "unresolved": [],
            "artifacts": [],
            "generation_mode": "llm" if provider != "mock" else "mock",
        }
        await session.commit()

        if turn.stop_reason == "interrupted":
            await transition(
                session, self.bus, run, RunStatus.CANCELLED, reason="Interrupted by you."
            )
            await session.commit()
            return
        await transition(session, self.bus, run, RunStatus.VERIFYING)
        run.verification = {
            "passed": True,
            "checks": [
                {"rule": "provider_turn_completed", "passed": True, "detail": turn.stop_reason}
            ],
        }
        await self.bus.emit(
            session,
            workspace_id=run.workspace_id,
            run_id=run.id,
            type=EventType.VERIFICATION_COMPLETED,
            payload={"passed": True},
        )
        await transition(session, self.bus, run, RunStatus.REVIEWING)
        run.review = {"passed": bool(turn.final_text.strip()), "notes": []}
        await transition(session, self.bus, run, RunStatus.COMPLETED)
        await session.commit()

    async def _chat_permission(
        self, session: AsyncSession, run: Run, tool_name: str, tool_input: dict[str, Any]
    ) -> tuple[bool, str, dict[str, Any]]:
        """Bridge a live provider tool request to the gateway.

        A live chat turn must NOT block a worker slot waiting on a human (review F4): if a
        requested tool needs approval, deny it here with a clear message and let the user run
        it as a skill (which parks cleanly on the approval queue instead of holding the
        worker). Chat today is only granted auto-allowed read-only tools, so this denies
        nothing that currently works — it removes a latent local-DoS, not a feature. Promoting
        chat to approval-gated tools requires session parking (see DECISIONS ADR-013).
        """
        try:
            result = await self.gateway.call_tool(
                session,
                run,
                tool_name,
                tool_input,
                purpose=f"Chat session wants to use {tool_name}",
                why="Requested live during your conversation.",
            )
            await session.commit()
            return result.ok, result.error or "", tool_input
        except ToolDenied as exc:
            await session.commit()
            return False, exc.reason, tool_input
        except ApprovalPending:
            # Roll back the pending approval/tool-call this attempt created so it doesn't
            # linger in the queue for a run that will not continue it.
            await session.rollback()
            return (
                False,
                "This action needs your approval, which isn't available inside a live chat "
                f"turn. Run “{tool_name}” as a skill so it goes through the approval queue.",
                tool_input,
            )

    # ------------------------------------------------------------------ shared

    def _route(self, text: str) -> str | None:
        lower = (text or "").lower()
        for slug, keywords in ROUTE_KEYWORDS.items():
            if any(k in lower for k in keywords):
                return slug
        for slug in self.registry.skills:
            if slug.replace("-", " ") in lower:
                return slug
        return None

    def _make_generator(self, ws: Any):
        if ws.provider != "claude":
            return None
        from cockpit.runtime.claude import ClaudeAgentRuntime, one_shot

        runtime = ClaudeAgentRuntime()
        ok, _ = runtime.available()
        if not ok:
            return None

        async def generate(prompt: str) -> str | None:
            try:
                return await one_shot(
                    prompt,
                    system_prompt="You are Otto, a careful analyst. Be concise and honest "
                    "about uncertainty.",
                )
            except Exception as exc:
                log.warning("one-shot generation failed: %s", exc)
                return None

        return generate

    async def _check_budgets(self, session: AsyncSession, run: Run, ws: Any) -> str | None:
        if run.budget_usd is None:
            run.budget_usd = ws.run_budget_usd
        day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        from sqlalchemy import func

        spent_today = (
            await session.scalar(
                select(func.coalesce(func.sum(Run.cost_usd), 0.0)).where(
                    Run.workspace_id == run.workspace_id, Run.created_at >= day_start
                )
            )
        ) or 0.0
        if spent_today >= ws.daily_budget_usd:
            return (
                f"Daily budget exhausted (${spent_today:.2f} of "
                f"${ws.daily_budget_usd:.2f}). Raise it in Settings → Budgets."
            )
        return None


# ---------------------------------------------------------------------- loop & recovery


async def claim_next_run(session: AsyncSession) -> Run | None:
    now = datetime.now(UTC)
    # Only ever consider UNCLAIMED queued runs. The claim UPDATE below sets worker_claim but
    # leaves status='queued' until process() flips it under the semaphore, so `worker_claim
    # IS NULL` (not status) is what makes this an honest compare-and-swap: a run already
    # claimed can neither be re-selected nor re-claimed, even under semaphore saturation
    # (review F3). worker_claim is cleared whenever a run re-enters `queued` (see
    # state_machine.transition) and for all queued runs at startup (recover_interrupted_runs).
    candidate = await session.scalar(
        select(Run)
        .where(
            Run.status == RunStatus.QUEUED.value,
            Run.worker_claim.is_(None),
            (Run.scheduled_for.is_(None)) | (Run.scheduled_for <= now),
        )
        .order_by(Run.created_at)
        .limit(1)
    )
    if candidate is None:
        return None
    result = await session.execute(
        update(Run)
        .where(
            Run.id == candidate.id,
            Run.status == RunStatus.QUEUED.value,
            Run.worker_claim.is_(None),
        )
        .values(worker_claim=WORKER_ID, heartbeat_at=now)
    )
    await session.commit()
    if getattr(result, "rowcount", 0) != 1:  # lost the race — another claimer won
        return None
    await session.refresh(candidate)
    return candidate


async def recover_interrupted_runs(session: AsyncSession, bus: EventBus) -> int:
    """On startup: in-flight runs from a dead process become `interrupted` (events kept)."""
    stale = (
        await session.scalars(
            select(Run).where(
                Run.status.in_(
                    [
                        RunStatus.TRIAGING.value,
                        RunStatus.PLANNING.value,
                        RunStatus.EXECUTING.value,
                        RunStatus.VERIFYING.value,
                        RunStatus.REVIEWING.value,
                    ]
                )
            )
        )
    ).all()
    for run in stale:
        await transition(
            session,
            bus,
            run,
            RunStatus.INTERRUPTED,
            reason="The control plane restarted while this run was in flight. "
            "Resume or restart it from History — completed external writes will "
            "not re-fire.",
        )
    # A run claimed by the now-dead worker but not yet started stays `queued` with a stale
    # worker_claim; clear those so this fresh process can claim them (review F3).
    await session.execute(
        update(Run)
        .where(Run.status == RunStatus.QUEUED.value, Run.worker_claim.is_not(None))
        .values(worker_claim=None)
    )
    await session.commit()
    return len(stale)


async def worker_loop(settings: Settings, *, stop: asyncio.Event) -> None:
    registry = get_registry()
    bus = get_bus()
    processor = RunProcessor(settings, registry, bus)
    semaphore = asyncio.Semaphore(settings.worker_concurrency)
    active: set[asyncio.Task[None]] = set()
    log.info("worker %s started (concurrency %d)", WORKER_ID, settings.worker_concurrency)

    from cockpit.db import db_session

    async def run_one(run_id: str) -> None:
        async with semaphore:
            async with db_session() as session:
                run = await session.get(Run, run_id)
                if run is not None:
                    await processor.process(session, run)

    while not stop.is_set():
        try:
            async with db_session() as session:
                run = await claim_next_run(session)
            if run is not None:
                task = asyncio.create_task(run_one(run.id))
                active.add(task)
                task.add_done_callback(active.discard)
                continue  # look for more work immediately
        except Exception:
            log.exception("worker loop iteration failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.worker_poll_seconds)
        except TimeoutError:
            pass
    if active:
        await asyncio.gather(*active, return_exceptions=True)
    log.info("worker stopped")


async def process_run_inline(run_id: str) -> None:
    """Deterministic single-run execution (used by tests and the demo seeder)."""
    from cockpit.db import db_session

    settings = get_registry().settings
    processor = RunProcessor(settings, get_registry(), get_bus())
    async with db_session() as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise ValueError(f"run {run_id} not found")
        await processor.process(session, run)


def json_default(obj: Any) -> str:
    return str(obj)


def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=json_default)
