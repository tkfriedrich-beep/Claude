"""API routers under /api/v1."""

from fastapi import APIRouter

from cockpit.api import approvals, catalog, content, runs, system

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
api_router.include_router(runs.router)
api_router.include_router(approvals.router)
api_router.include_router(catalog.router)
api_router.include_router(content.router)
