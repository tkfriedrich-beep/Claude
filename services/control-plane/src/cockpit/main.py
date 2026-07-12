"""FastAPI app assembly: middleware, problem responses, lifespan (worker/scheduler/recovery)."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import cockpit
from cockpit.api import api_router
from cockpit.config import get_settings
from cockpit.db import apply_sqlite_pragmas, db_session, init_engine
from cockpit.events import get_bus
from cockpit.ids import correlation_id as new_correlation_id
from cockpit.logging import get_logger, setup_logging
from cockpit.registry import get_registry
from cockpit.scheduler import scheduler_loop
from cockpit.worker import recover_interrupted_runs, worker_loop
from cockpit.workspace import get_default_workspace

log = get_logger("cockpit.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging()
    engine = init_engine(settings)
    await apply_sqlite_pragmas(engine)

    registry = get_registry()
    async with db_session() as session:
        workspace = await get_default_workspace(session)
        if workspace is not None:
            await registry.sync_workspace(session, workspace.id)
            await registry.run_health_checks(session, workspace.id)
            recovered = await recover_interrupted_runs(session, get_bus())
            if recovered:
                log.info("marked %d in-flight runs as interrupted after restart", recovered)
        await session.commit()

    stop = asyncio.Event()
    tasks: list[asyncio.Task[None]] = []
    if settings.start_background_tasks:
        tasks = [
            asyncio.create_task(worker_loop(settings, stop=stop), name="worker"),
            asyncio.create_task(scheduler_loop(settings, stop=stop), name="scheduler"),
        ]
    try:
        yield
    finally:
        stop.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="AgenticOS Cockpit Control Plane",
        version=cockpit.__version__,
        lifespan=lifespan,
        docs_url="/api/v1/docs",
        openapi_url="/api/v1/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-Id"],
    )

    @app.middleware("http")
    async def correlation_middleware(request: Request, call_next: Any):
        cid = request.headers.get("X-Correlation-Id") or new_correlation_id()
        request.state.correlation_id = cid
        response = await call_next(request)
        response.headers["X-Correlation-Id"] = cid
        return response

    @app.exception_handler(HTTPException)
    async def problem_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "type": "about:blank",
                "title": exc.detail if isinstance(exc.detail, str) else "Error",
                "status": exc.status_code,
                "detail": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
                "correlation_id": getattr(request.state, "correlation_id", None),
            },
            media_type="application/problem+json",
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", []))
        return JSONResponse(
            status_code=422,
            content={
                "type": "about:blank",
                "title": "Request validation failed",
                "status": 422,
                "detail": f"{loc}: {first.get('msg', 'invalid')}",
                "correlation_id": getattr(request.state, "correlation_id", None),
            },
            media_type="application/problem+json",
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error on %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "type": "about:blank",
                "title": "Internal error",
                "status": 500,
                "detail": "Something went wrong in the control plane. Check its logs.",
                "correlation_id": getattr(request.state, "correlation_id", None),
            },
            media_type="application/problem+json",
        )

    app.include_router(api_router)
    return app


app = create_app()
