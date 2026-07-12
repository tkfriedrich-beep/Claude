"""Shared API dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from cockpit.db import session_factory
from cockpit.models import Workspace
from cockpit.workspace import get_default_workspace


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory()() as session:
        yield session


async def get_workspace(session: AsyncSession = Depends(get_session)) -> Workspace:
    ws = await get_default_workspace(session)
    if ws is None:
        raise HTTPException(
            status_code=409,
            detail="No workspace yet — complete onboarding first (POST /api/v1/onboarding).",
        )
    return ws


def get_correlation_id(request: Request) -> str:
    return getattr(request.state, "correlation_id", "")
