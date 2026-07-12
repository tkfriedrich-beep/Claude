"""Commands, sessions, runs, and the SSE event stream."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cockpit.api.deps import get_session, get_workspace
from cockpit.enums import EventType, RunStatus
from cockpit.events import event_to_dict, get_bus
from cockpit.ids import correlation_id, new_id
from cockpit.models import ProviderSession, Run, RunEvent, Workspace
from cockpit.runtime import get_runtime
from cockpit.runtime.base import SessionContext
from cockpit.schemas import CommandRequest, EventOut, RunOut, SessionOut
from cockpit.state_machine import InvalidTransition, transition
from cockpit.workspace import get_workspace_settings

router = APIRouter(tags=["runs"])


@router.post("/commands", response_model=RunOut, status_code=201)
async def submit_command(
    body: CommandRequest,
    request: Request,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> Run:
    ws = await get_workspace_settings(session, workspace.id)
    if ws.kill_switch:
        raise HTTPException(423, "Kill switch is engaged — release it in Settings to run anything.")
    if not body.text.strip() and not body.skill_slug:
        raise HTTPException(400, "Provide command text or a skill to run.")

    kind = "skill" if body.skill_slug else "chat"
    run = Run(
        id=new_id("run"),
        workspace_id=workspace.id,
        kind=kind,
        status=RunStatus.QUEUED.value,
        title=body.title
        or (body.text.strip()[:80] if body.text.strip() else body.skill_slug or "Run"),
        skill_slug=body.skill_slug,
        session_id=body.session_id,
        command_text=body.text,
        input=body.input,
        mode=body.mode,
        domain_key=body.domain_key,
        context_pack_id=body.context_pack_id,
        budget_usd=body.budget_usd,
        correlation_id=request.headers.get("X-Correlation-Id") or correlation_id(),
    )
    session.add(run)
    await session.flush()
    await get_bus().emit(
        session,
        workspace_id=workspace.id,
        run_id=run.id,
        type=EventType.RUN_QUEUED,
        payload={"kind": kind, "mode": body.mode},
    )
    await session.commit()
    return run


@router.get("/runs", response_model=list[RunOut])
async def list_runs(
    status: str | None = None,
    kind: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> list[Run]:
    query = select(Run).where(Run.workspace_id == workspace.id)
    if status:
        query = query.where(Run.status.in_(status.split(",")))
    if kind:
        query = query.where(Run.kind == kind)
    query = query.order_by(Run.created_at.desc()).limit(limit).offset(offset)
    return list((await session.scalars(query)).all())


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run(
    run_id: str,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> Run:
    run = await session.get(Run, run_id)
    if run is None or run.workspace_id != workspace.id:
        raise HTTPException(404, "Run not found")
    return run


@router.get("/runs/{run_id}/events", response_model=list[EventOut])
async def get_run_events(
    run_id: str,
    since: int = 0,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> list[RunEvent]:
    return list(
        (
            await session.scalars(
                select(RunEvent)
                .where(
                    RunEvent.run_id == run_id,
                    RunEvent.workspace_id == workspace.id,
                    RunEvent.id > since,
                )
                .order_by(RunEvent.id)
            )
        ).all()
    )


async def _act_on_run(
    session: AsyncSession, workspace: Workspace, run_id: str, to: RunStatus, reason: str
) -> Run:
    run = await session.get(Run, run_id)
    if run is None or run.workspace_id != workspace.id:
        raise HTTPException(404, "Run not found")
    try:
        await transition(session, get_bus(), run, to, reason=reason)
    except InvalidTransition as exc:
        raise HTTPException(409, str(exc)) from exc
    await session.commit()
    return run


@router.post("/runs/{run_id}/cancel", response_model=RunOut)
async def cancel_run(
    run_id: str,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> Run:
    run = await session.get(Run, run_id)
    if run is None or run.workspace_id != workspace.id:
        raise HTTPException(404, "Run not found")
    # Live chat turns: also interrupt the provider so streaming stops quickly.
    if run.kind == "chat" and run.session_id and run.provider:
        try:
            runtime = get_runtime(run.provider)
            await runtime.interrupt(_session_ctx_stub(run))
        except Exception:  # provider may be gone; the FSM cancel still applies
            pass
    return await _act_on_run(session, workspace, run_id, RunStatus.CANCELLED, "Cancelled by you.")


@router.post("/runs/{run_id}/interrupt", response_model=RunOut)
async def interrupt_run(
    run_id: str,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> Run:
    run = await session.get(Run, run_id)
    if run is None or run.workspace_id != workspace.id:
        raise HTTPException(404, "Run not found")
    if run.kind == "chat" and run.session_id and run.provider:
        try:
            await get_runtime(run.provider).interrupt(_session_ctx_stub(run))
        except Exception:
            pass
        return run  # chat runs settle to cancelled via the worker's stop_reason
    return await _act_on_run(
        session, workspace, run_id, RunStatus.INTERRUPTED, "Interrupted by you."
    )


@router.post("/runs/{run_id}/resume", response_model=RunOut)
async def resume_run(
    run_id: str,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> Run:
    return await _act_on_run(
        session,
        workspace,
        run_id,
        RunStatus.QUEUED,
        "Resumed — completed steps replay from the audit log; external writes will not re-fire.",
    )


def _session_ctx_stub(run: Run) -> SessionContext:
    return SessionContext(
        workspace_id=run.workspace_id,
        internal_session_id=run.session_id or "",
        external_session_id=None,
        system_prompt="",
        workspace_roots=[],
    )


# ---------------------------------------------------------------- sessions


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> list[ProviderSession]:
    return list(
        (
            await session.scalars(
                select(ProviderSession)
                .where(ProviderSession.workspace_id == workspace.id)
                .order_by(ProviderSession.last_active_at.desc())
                .limit(30)
            )
        ).all()
    )


@router.get("/sessions/{session_id}/runs", response_model=list[RunOut])
async def session_runs(
    session_id: str,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> list[Run]:
    return list(
        (
            await session.scalars(
                select(Run)
                .where(Run.workspace_id == workspace.id, Run.session_id == session_id)
                .order_by(Run.created_at)
            )
        ).all()
    )


# ---------------------------------------------------------------- SSE


@router.get("/events/stream")
async def event_stream(
    request: Request,
    run_id: str | None = None,
    since: int | None = Query(default=None),
    workspace: Workspace = Depends(get_workspace),
) -> StreamingResponse:
    bus = get_bus()
    last_id_header = request.headers.get("Last-Event-ID")
    backfill_from = (
        since
        if since is not None
        else (int(last_id_header) if last_id_header and last_id_header.isdigit() else None)
    )

    async def generator():
        queue = bus.subscribe(run_id)
        try:
            yield ": connected\n\n"
            if backfill_from is not None:
                from cockpit.db import db_session

                async with db_session() as session:
                    query = (
                        select(RunEvent)
                        .where(RunEvent.workspace_id == workspace.id, RunEvent.id > backfill_from)
                        .order_by(RunEvent.id)
                        .limit(500)
                    )
                    if run_id:
                        query = query.where(RunEvent.run_id == run_id)
                    for event in (await session.scalars(query)).all():
                        yield _sse(event_to_dict(event))
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield _sse(data)
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            bus.unsubscribe(queue, run_id)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _sse(data: dict[str, Any]) -> str:
    return (
        f"id: {data['id']}\nevent: {data['type']}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    )
