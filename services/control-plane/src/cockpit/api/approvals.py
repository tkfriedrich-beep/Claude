"""Approvals — list and resolve. Resolution re-queues the paused run (gateway replays)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cockpit.api.deps import get_session, get_workspace
from cockpit.enums import ApprovalStatus, EventType, RunStatus, ToolCallStatus
from cockpit.events import get_bus
from cockpit.logging import SENSITIVE_VALUE_RE
from cockpit.models import Approval, Run, ToolCall, Workspace
from cockpit.schemas import ApprovalOut, ApprovalResolveRequest
from cockpit.state_machine import transition

router = APIRouter(tags=["approvals"])

CONFIRM_PHRASE = "I understand the risk"


@router.get("/approvals", response_model=list[ApprovalOut])
async def list_approvals(
    status: str | None = None,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> list[Approval]:
    query = select(Approval).where(Approval.workspace_id == workspace.id)
    if status:
        query = query.where(Approval.status.in_(status.split(",")))
    query = query.order_by(Approval.requested_at.desc()).limit(100)
    approvals = list((await session.scalars(query)).all())
    # surface expiry lazily so the UI never shows an actionable-but-stale card
    now = datetime.now(UTC)
    changed = False
    for approval in approvals:
        if (
            approval.status == ApprovalStatus.PENDING.value
            and approval.expires_at
            and approval.expires_at < now
        ):
            approval.status = ApprovalStatus.EXPIRED.value
            approval.resolved_at = now
            changed = True
    if changed:
        await session.commit()
    return approvals


@router.post("/approvals/{approval_id}/resolve", response_model=ApprovalOut)
async def resolve_approval(
    approval_id: str,
    body: ApprovalResolveRequest,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> Approval:
    approval = await session.get(Approval, approval_id)
    if approval is None or approval.workspace_id != workspace.id:
        raise HTTPException(404, "Approval not found")
    if approval.status != ApprovalStatus.PENDING.value:
        raise HTTPException(409, f"Approval already {approval.status}.")
    now = datetime.now(UTC)
    if approval.expires_at and approval.expires_at < now:
        approval.status = ApprovalStatus.EXPIRED.value
        approval.resolved_at = now
        await session.commit()
        raise HTTPException(
            410,
            "This approval expired — the action was not executed. "
            "Re-run the skill for a fresh proposal.",
        )
    if body.decision == "approve" and approval.confirm_phrase_required:
        if (body.confirm_phrase or "").strip() != CONFIRM_PHRASE:
            raise HTTPException(
                428,
                f"High-impact action: type the confirmation phrase “{CONFIRM_PHRASE}” to approve.",
            )

    approval.status = (
        ApprovalStatus.APPROVED if body.decision == "approve" else ApprovalStatus.DENIED
    ).value
    approval.resolved_at = now
    approval.decision_note = body.note
    approval.resolved_by = "owner"

    tool_call = (
        await session.get(ToolCall, approval.tool_call_id) if approval.tool_call_id else None
    )
    if tool_call is not None:
        if body.decision == "approve":
            tool_call.status = ToolCallStatus.APPROVED.value
            if body.edited_input is not None:
                # The edited input is the EXECUTABLE source of truth on resume, so it must be
                # stored raw — persisting a redacted copy meant the run later wrote the literal
                # mask to disk and reported success (review R3-F10). To still honor R2-F5 (no raw
                # secret in the audit DB), reject credential-shaped input instead of masking it:
                # tool input should carry secret *references*, not raw values.
                if SENSITIVE_VALUE_RE.search(json.dumps(body.edited_input, default=str)):
                    raise HTTPException(
                        422,
                        "That edited input looks like it contains a raw credential. Tool input "
                        "must reference secrets by name, not embed their values.",
                    )
                tool_call.edited_input = body.edited_input
        else:
            tool_call.status = ToolCallStatus.DENIED.value
            tool_call.error = body.note or "You denied this action."

    run = await session.get(Run, approval.run_id)
    if run is not None:
        approval_wait = (now - approval.requested_at).total_seconds()
        run.approval_wait_seconds += max(approval_wait, 0.0)
        await get_bus().emit(
            session,
            workspace_id=workspace.id,
            run_id=run.id,
            type=EventType.APPROVAL_RESOLVED,
            payload={
                "approval_id": approval.id,
                "decision": body.decision,
                "title": approval.title,
                "note": body.note,
            },
        )
        # Skill runs parked on this approval continue by re-queueing (worker replays).
        if RunStatus(run.status) is RunStatus.AWAITING_APPROVAL and run.kind == "skill":
            await transition(
                session, get_bus(), run, RunStatus.QUEUED, reason=f"approval {body.decision}d"
            )
    await session.commit()
    return approval
