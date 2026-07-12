"""Demo seeder — creates a demo workspace and runs REAL skill runs over demo data.

Honesty rule: we never fabricate run history. The seeded history entries are genuine pipeline
executions (Project Pulse, Business Idea Triage in draft mode) against data/demo content, and
an MCP demo server + a shadow automation are registered so every screen has real state.
Idempotent: safe to run repeatedly.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from cockpit.config import get_settings
from cockpit.db import apply_sqlite_pragmas, db_session, init_engine
from cockpit.enums import EventType, RunStatus
from cockpit.events import get_bus
from cockpit.ids import correlation_id, new_id
from cockpit.logging import get_logger, setup_logging
from cockpit.models import Commitment, Connector, Person, Project, Run, Schedule
from cockpit.registry import get_registry
from cockpit.workspace import get_default_workspace

log = get_logger("cockpit.demo")


async def seed_demo_content(workspace_id: str) -> None:
    """Seed projects/people/commitments + demo MCP server + shadow automation + 2 real runs."""
    async with db_session() as session:
        # projects mirroring the demo vault
        existing = {
            p.slug
            for p in (
                await session.scalars(select(Project).where(Project.workspace_id == workspace_id))
            ).all()
        }
        demo_projects = [
            (
                "website-relaunch",
                "Website Relaunch",
                "work",
                "projects/website-relaunch.md",
                "Ship the new marketing site.",
            ),
            (
                "q3-consulting-pipeline",
                "Q3 Consulting Pipeline",
                "work",
                "projects/q3-consulting-pipeline.md",
                "Fill Q3 with 3 anchor clients.",
            ),
            (
                "home-office-studio",
                "Home Office Studio",
                "personal",
                "projects/home-office-studio.md",
                "Turn the spare room into a studio.",
            ),
        ]
        for slug, name, domain, path, desc in demo_projects:
            if slug not in existing:
                session.add(
                    Project(
                        id=new_id("prj"),
                        workspace_id=workspace_id,
                        name=name,
                        slug=slug,
                        domain_key=domain,
                        path=path,
                        description=desc,
                    )
                )

        if not (
            await session.scalars(select(Person).where(Person.workspace_id == workspace_id))
        ).first():
            session.add_all(
                [
                    Person(
                        id=new_id("per"),
                        workspace_id=workspace_id,
                        name="Maya Lindholm",
                        relation="Design partner (Website Relaunch)",
                        notes="Prefers async Looms; reviews Tue/Thu.",
                        source_ref="data/demo/vault/projects/website-relaunch.md",
                    ),
                    Person(
                        id=new_id("per"),
                        workspace_id=workspace_id,
                        name="Jonas Petersen",
                        relation="Prospect — Nordwind Logistics",
                        notes="Interested in ops-automation audit; follow up after pilot scope.",
                        source_ref="data/demo/vault/projects/q3-consulting-pipeline.md",
                    ),
                    Person(
                        id=new_id("per"),
                        workspace_id=workspace_id,
                        name="Sofia Keller",
                        relation="Accountant",
                        notes="Quarterly VAT filing reminders; send docs by the 5th.",
                        source_ref="data/demo/vault/wiki/finances-overview.md",
                    ),
                ]
            )

        if not (
            await session.scalars(select(Commitment).where(Commitment.workspace_id == workspace_id))
        ).first():
            now = datetime.now(UTC)
            session.add_all(
                [
                    Commitment(
                        id=new_id("cmt"),
                        workspace_id=workspace_id,
                        title="Send Maya the revised homepage copy",
                        due_at=now + timedelta(hours=20),
                        source_ref="data/demo/vault/projects/website-relaunch.md",
                    ),
                    Commitment(
                        id=new_id("cmt"),
                        workspace_id=workspace_id,
                        title="Follow up with Jonas on pilot scope",
                        due_at=now + timedelta(days=1, hours=4),
                        source_ref="data/demo/vault/projects/q3-consulting-pipeline.md",
                    ),
                    Commitment(
                        id=new_id("cmt"),
                        workspace_id=workspace_id,
                        title="Book studio electrician quote",
                        due_at=now + timedelta(days=5),
                        source_ref="data/demo/vault/projects/home-office-studio.md",
                    ),
                ]
            )

        # demo MCP server (in-process; proves the registry without subprocesses)
        mcp_row = await session.scalar(
            select(Connector).where(Connector.workspace_id == workspace_id, Connector.slug == "mcp")
        )
        if mcp_row is not None:
            servers = list(mcp_row.config.get("servers", []))
            if not any(s["name"] == "demo-tools" for s in servers):
                servers.append(
                    {
                        "name": "demo-tools",
                        "transport": "inproc",
                        "enabled": True,
                        "description": "Built-in demo MCP server (echo, todo_add).",
                    }
                )
                mcp_row.config = {**mcp_row.config, "servers": servers}

        registry = get_registry()
        await registry.refresh_runtime_config(session, workspace_id)
        await registry.run_health_checks(session, workspace_id)

        # a shadow-mode automation for Morning Brief (daily)
        if not (
            await session.scalars(select(Schedule).where(Schedule.workspace_id == workspace_id))
        ).first():
            session.add(
                Schedule(
                    id=new_id("sch"),
                    workspace_id=workspace_id,
                    skill_slug="morning-brief",
                    name="Morning Brief (daily, shadow)",
                    interval_minutes=1440,
                    shadow_mode=True,
                    enabled=True,
                    next_run_at=datetime.now(UTC) + timedelta(hours=12),
                )
            )
        await session.commit()

    # real runs over demo data → honest history + artifacts
    await _run_skill_now(workspace_id, "project-pulse", mode="draft")
    await _run_skill_now(workspace_id, "business-idea-triage", mode="draft")

    # knowledge index
    async with db_session() as session:
        from cockpit.knowledge import get_retrieval_provider

        count = await get_retrieval_provider().reindex(session, workspace_id)
        log.info("knowledge index built: %d documents", count)


async def _run_skill_now(workspace_id: str, slug: str, *, mode: str) -> None:
    from cockpit.worker import process_run_inline

    async with db_session() as session:
        already = await session.scalar(
            select(Run).where(
                Run.workspace_id == workspace_id,
                Run.skill_slug == slug,
                Run.status == RunStatus.COMPLETED.value,
            )
        )
        if already is not None:
            return
        run = Run(
            id=new_id("run"),
            workspace_id=workspace_id,
            kind="skill",
            status=RunStatus.QUEUED.value,
            title=f"{slug} (demo seed)",
            skill_slug=slug,
            mode=mode,
            correlation_id=correlation_id(),
        )
        session.add(run)
        await session.flush()
        await get_bus().emit(
            session,
            workspace_id=workspace_id,
            run_id=run.id,
            type=EventType.RUN_QUEUED,
            payload={"skill": slug, "seed": True},
        )
        await session.commit()
        run_id = run.id
    await process_run_inline(run_id)
    log.info("demo seed run %s (%s) executed", run_id, slug)


async def _main() -> None:
    setup_logging()
    settings = get_settings()
    engine = init_engine(settings)
    await apply_sqlite_pragmas(engine)

    async with db_session() as session:
        workspace = await get_default_workspace(session)
        if workspace is None:
            # CLI path: create the demo workspace via the same code onboarding uses.
            from cockpit.api.system import onboarding
            from cockpit.schemas import OnboardingRequest

            log.info("no workspace — creating demo workspace")
            await onboarding(
                OnboardingRequest(
                    user_name="Alex", assistant_name="Otto", enable_demo_data=True, safe_mode=True
                ),
                session,
            )
            print(
                "Demo workspace created and seeded. Start `make dev` and open http://localhost:3000"
            )
            return
        ws_id = workspace.id
    await seed_demo_content(ws_id)
    print("Demo content ensured (idempotent). Open http://localhost:3000")


if __name__ == "__main__":
    asyncio.run(_main())
