"""Artifacts, memories, briefing, agenda, projects, people, knowledge search."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cockpit.api.deps import get_session, get_workspace
from cockpit.briefing import build_briefing
from cockpit.config import get_settings
from cockpit.ids import new_id
from cockpit.knowledge import get_retrieval_provider
from cockpit.models import (
    Artifact,
    Commitment,
    Memory,
    MemorySource,
    Person,
    Project,
    Workspace,
)
from cockpit.schemas import ArtifactOut, MemoryOut, MemoryPatchRequest
from cockpit.workspace import get_workspace_settings

router = APIRouter(tags=["content"])


@router.get("/briefing")
async def briefing(
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await build_briefing(session, workspace.id)


@router.get("/agenda")
async def agenda(
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    ws = await get_workspace_settings(session, workspace.id)
    events: list[dict[str, Any]] = []
    demo = False
    if ws.demo_mode:
        import json as _json

        path = get_settings().demo_dir / "agenda.json"
        if path.exists():
            events = _json.loads(path.read_text(encoding="utf-8")).get("events", [])
            demo = True
    commitments = (
        await session.scalars(
            select(Commitment)
            .where(Commitment.workspace_id == workspace.id, Commitment.status == "open")
            .order_by(Commitment.due_at.is_(None), Commitment.due_at)
        )
    ).all()
    return {
        "events": events,
        "events_demo": demo,
        "commitments": [
            {
                "id": c.id,
                "title": c.title,
                "due_at": c.due_at.isoformat() if c.due_at else None,
                "source_ref": c.source_ref,
            }
            for c in commitments
        ],
    }


@router.get("/projects")
async def list_projects(
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    projects = (
        await session.scalars(
            select(Project)
            .where(Project.workspace_id == workspace.id)
            .order_by(Project.updated_at.desc())
        )
    ).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "slug": p.slug,
            "status": p.status,
            "domain_key": p.domain_key,
            "path": p.path,
            "description": p.description,
            "updated_at": (p.updated_at or p.created_at).isoformat(),
        }
        for p in projects
    ]


@router.get("/people")
async def list_people(
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    people = (
        await session.scalars(
            select(Person).where(Person.workspace_id == workspace.id).order_by(Person.name)
        )
    ).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "relation": p.relation,
            "notes": p.notes,
            "source_ref": p.source_ref,
        }
        for p in people
    ]


@router.get("/knowledge/search")
async def knowledge_search(
    q: str,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    results = await get_retrieval_provider().search(session, workspace.id, q)
    return {"query": q, "results": results}


@router.post("/knowledge/reindex")
async def knowledge_reindex(
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    count = await get_retrieval_provider().reindex(session, workspace.id)
    return {"indexed": count}


# ---------------------------------------------------------------- artifacts


@router.get("/artifacts", response_model=list[ArtifactOut])
async def list_artifacts(
    run_id: str | None = None,
    limit: int = 50,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> list[Artifact]:
    query = select(Artifact).where(Artifact.workspace_id == workspace.id)
    if run_id:
        query = query.where(Artifact.run_id == run_id)
    query = query.order_by(Artifact.created_at.desc()).limit(min(limit, 200))
    return list((await session.scalars(query)).all())


@router.get("/artifacts/{artifact_id}")
async def get_artifact(
    artifact_id: str,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    artifact = await session.get(Artifact, artifact_id)
    if artifact is None or artifact.workspace_id != workspace.id:
        raise HTTPException(404, "Artifact not found")
    path = get_settings().artifacts_dir / artifact.path
    content = path.read_text(encoding="utf-8") if path.exists() else None
    return {
        "id": artifact.id,
        "run_id": artifact.run_id,
        "kind": artifact.kind,
        "title": artifact.title,
        "mime": artifact.mime,
        "meta": artifact.meta,
        "created_at": artifact.created_at.isoformat(),
        "content": content,
        "missing_file": content is None,
    }


@router.get("/artifacts/{artifact_id}/download")
async def download_artifact(
    artifact_id: str,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    artifact = await session.get(Artifact, artifact_id)
    if artifact is None or artifact.workspace_id != workspace.id:
        raise HTTPException(404, "Artifact not found")
    path = get_settings().artifacts_dir / artifact.path
    if not path.exists():
        raise HTTPException(410, "Artifact file is missing on disk")
    return FileResponse(path, media_type=artifact.mime, filename=path.name)


# ---------------------------------------------------------------- memories


@router.get("/memories", response_model=list[MemoryOut])
async def list_memories(
    status: str | None = None,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> list[Memory]:
    query = select(Memory).where(Memory.workspace_id == workspace.id)
    if status:
        query = query.where(Memory.status.in_(status.split(",")))
    query = query.order_by(Memory.created_at.desc()).limit(200)
    return list((await session.scalars(query)).all())


@router.get("/memories/export")
async def export_memories(
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    memories = (
        await session.scalars(select(Memory).where(Memory.workspace_id == workspace.id))
    ).all()
    sources = (
        await session.scalars(select(MemorySource).where(MemorySource.workspace_id == workspace.id))
    ).all()
    by_memory: dict[str, list[dict[str, str]]] = {}
    for s in sources:
        by_memory.setdefault(s.memory_id, []).append(
            {"source_type": s.source_type, "reference": s.reference, "excerpt": s.excerpt}
        )
    payload = {
        "exported_at": datetime.now(UTC).isoformat(),
        "memories": [
            {
                "id": m.id,
                "kind": m.kind,
                "status": m.status,
                "content": m.content,
                "structured": m.structured,
                "confidence": m.confidence,
                "sensitivity": m.sensitivity,
                "domain": m.domain_key,
                "rationale": m.rationale,
                "created_at": m.created_at.isoformat(),
                "sources": by_memory.get(m.id, []),
            }
            for m in memories
        ],
    }
    return JSONResponse(
        payload,
        headers={"Content-Disposition": 'attachment; filename="memories-export.json"'},
    )


@router.patch("/memories/{memory_id}", response_model=MemoryOut)
async def review_memory(
    memory_id: str,
    body: MemoryPatchRequest,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> Memory:
    memory = await session.get(Memory, memory_id)
    if memory is None or memory.workspace_id != workspace.id:
        raise HTTPException(404, "Memory not found")
    if body.content is not None:
        memory.content = body.content
    if body.action == "approve":
        memory.status = "active"
        memory.verified_at = datetime.now(UTC)
        # Approved commitment memories become real commitments (structured state).
        if memory.kind == "commitment":
            first_source = await session.scalar(
                select(MemorySource).where(MemorySource.memory_id == memory.id)
            )
            session.add(
                Commitment(
                    id=new_id("cmt"),
                    workspace_id=workspace.id,
                    title=memory.content,
                    source_ref=first_source.reference if first_source else None,
                )
            )
    else:
        memory.status = "rejected"
    await session.commit()
    return memory


@router.delete("/memories/{memory_id}", status_code=204)
async def delete_memory(
    memory_id: str,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> None:
    memory = await session.get(Memory, memory_id)
    if memory is None or memory.workspace_id != workspace.id:
        raise HTTPException(404, "Memory not found")
    for source in (
        await session.scalars(select(MemorySource).where(MemorySource.memory_id == memory.id))
    ).all():
        await session.delete(source)
    await session.delete(memory)
    await session.commit()
