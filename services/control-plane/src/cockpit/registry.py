"""Skill & connector registries.

Definitions live in the repo (skills/<id>/, connectors/<id>/manifest.yaml); the registry loads
them at startup, syncs DB rows (per workspace), and hands out live connector instances.
Connector runtime_config (vault path, registered webhooks, MCP servers) is refreshed from
workspace settings + connector rows whenever they change.
"""

from __future__ import annotations

import json
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cockpit.config import Settings
from cockpit.connectors.base import BaseConnector, ExecutionContext, HealthStatus
from cockpit.connectors.local_files import LocalFilesConnector
from cockpit.connectors.mcp import MCPConnector
from cockpit.connectors.mocks import (
    GitHubMockConnector,
    GoogleWorkspaceMockConnector,
    NotionMockConnector,
)
from cockpit.connectors.n8n import N8nConnector
from cockpit.connectors.obsidian import ObsidianConnector
from cockpit.enums import ConnectorHealthState
from cockpit.ids import new_id
from cockpit.logging import get_logger
from cockpit.models import Connector, ConnectorTool, Skill, SkillVersion, utcnow
from cockpit.workspace import get_workspace_settings

log = get_logger("cockpit.registry")

CONNECTOR_CLASSES: list[type[BaseConnector]] = [
    LocalFilesConnector,
    ObsidianConnector,
    N8nConnector,
    MCPConnector,
    GoogleWorkspaceMockConnector,
    NotionMockConnector,
    GitHubMockConnector,
]


class SkillDef:
    def __init__(self, manifest: dict[str, Any]) -> None:
        self.manifest = manifest

    @property
    def slug(self) -> str:
        return str(self.manifest["id"])

    @property
    def allowed_tools(self) -> list[str]:
        return list(self.manifest.get("allowed_tools", []))


class Registry:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.connectors: dict[str, BaseConnector] = {}
        self.skills: dict[str, SkillDef] = {}

    # ---------- loading from repo ----------

    def load(self) -> None:
        self.connectors = {}
        for cls in CONNECTOR_CLASSES:
            try:
                connector = cls(self.settings.connectors_dir)
                self.connectors[connector.slug] = connector
            except Exception:
                log.exception("failed to load connector %s", cls.slug)

        self.skills = {}
        for manifest_path in sorted(self.settings.skills_dir.glob("*/manifest.yaml")):
            try:
                manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
                skill_dir = manifest_path.parent
                for key, fname in (
                    ("input_schema", "input.schema.json"),
                    ("output_schema", "output.schema.json"),
                ):
                    schema_path = skill_dir / fname
                    if key not in manifest and schema_path.exists():
                        manifest[key] = json.loads(schema_path.read_text(encoding="utf-8"))
                skill = SkillDef(manifest)
                known_tools = self._all_tool_ids()
                unknown = [
                    t
                    for t in skill.allowed_tools
                    if t not in known_tools and not t.startswith(("n8n.", "mcp."))
                ]
                if unknown:
                    log.error(
                        "skill %s references unknown tools %s — skipping", skill.slug, unknown
                    )
                    continue
                self.skills[skill.slug] = skill
            except Exception:
                log.exception("failed to load skill manifest %s", manifest_path)
        log.info(
            "registry loaded: %d connectors, %d skills", len(self.connectors), len(self.skills)
        )

    def _all_tool_ids(self) -> set[str]:
        ids: set[str] = set()
        for connector in self.connectors.values():
            ids.update(t.id for t in connector.list_tools())
        return ids

    # ---------- DB sync ----------

    async def sync_workspace(self, session: AsyncSession, workspace_id: str) -> None:
        await self._sync_connectors(session, workspace_id)
        await self._sync_skills(session, workspace_id)
        await self.refresh_runtime_config(session, workspace_id)

    async def _sync_connectors(self, session: AsyncSession, workspace_id: str) -> None:
        for slug, connector in self.connectors.items():
            manifest = connector.get_manifest()
            row = await session.scalar(
                select(Connector).where(
                    Connector.workspace_id == workspace_id, Connector.slug == slug
                )
            )
            if row is None:
                row = Connector(
                    id=new_id("con"),
                    workspace_id=workspace_id,
                    slug=slug,
                    name=manifest.name,
                    category=manifest.category,
                    mode=manifest.default_mode.value,
                    enabled=True,
                    health=ConnectorHealthState.UNKNOWN.value,
                )
                session.add(row)
            row.name = manifest.name
            row.category = manifest.category
            row.manifest = manifest.model_dump(mode="json", exclude={"tools"})
            await session.flush()
            await self._sync_tools(session, workspace_id, connector)

    async def _sync_tools(
        self, session: AsyncSession, workspace_id: str, connector: BaseConnector
    ) -> None:
        existing = {
            t.tool_id: t
            for t in (
                await session.scalars(
                    select(ConnectorTool).where(
                        ConnectorTool.workspace_id == workspace_id,
                        ConnectorTool.connector_slug == connector.slug,
                    )
                )
            ).all()
        }
        current_ids = set()
        for tool in connector.list_tools():
            current_ids.add(tool.id)
            row = existing.get(tool.id)
            if row is None:
                row = ConnectorTool(
                    id=new_id("ct"),
                    workspace_id=workspace_id,
                    connector_slug=connector.slug,
                    tool_id=tool.id,
                )
                session.add(row)
            row.name = tool.name or tool.id
            row.version = tool.version
            row.access = tool.access.value
            row.risk_level = tool.risk_level.value
            row.external_side_effects = tool.external_side_effects
            row.manifest = tool.model_dump(mode="json")
        for tool_id, row in existing.items():
            if tool_id not in current_ids:
                row.enabled = False  # tool disappeared (e.g. webhook removed)
        await session.flush()

    async def _sync_skills(self, session: AsyncSession, workspace_id: str) -> None:
        for slug, skill in self.skills.items():
            m = skill.manifest
            row = await session.scalar(
                select(Skill).where(Skill.workspace_id == workspace_id, Skill.slug == slug)
            )
            if row is None:
                row = Skill(
                    id=new_id("skl"),
                    workspace_id=workspace_id,
                    slug=slug,
                    autonomy=int(m.get("default_autonomy", 3)),
                )
                session.add(row)
            row.name = m.get("name", slug)
            row.description = m.get("description", "")
            row.version = str(m.get("version", "0.1.0"))
            row.risk_level = m.get("risk_level", "R2")
            row.domains = m.get("domains", [])
            row.manifest = m
            version_exists = await session.scalar(
                select(SkillVersion).where(
                    SkillVersion.workspace_id == workspace_id,
                    SkillVersion.skill_slug == slug,
                    SkillVersion.version == row.version,
                )
            )
            if version_exists is None:
                session.add(
                    SkillVersion(
                        id=new_id("skv"),
                        workspace_id=workspace_id,
                        skill_slug=slug,
                        version=row.version,
                        manifest=m,
                    )
                )
        await session.flush()

    # ---------- runtime config & health ----------

    async def refresh_runtime_config(self, session: AsyncSession, workspace_id: str) -> None:
        ws = await get_workspace_settings(session, workspace_id)
        vault = ws.vault_path or (str(self.settings.demo_dir / "vault") if ws.demo_mode else None)
        obsidian = self.connectors.get("obsidian")
        if obsidian is not None:
            obsidian.runtime_config = {"vault_path": vault}  # type: ignore[attr-defined]
        for slug in ("n8n", "mcp"):
            inst = self.connectors.get(slug)
            if inst is None:
                continue
            row = await session.scalar(
                select(Connector).where(
                    Connector.workspace_id == workspace_id, Connector.slug == slug
                )
            )
            inst.runtime_config = dict(row.config) if row is not None else {}  # type: ignore[attr-defined]
        # dynamic tools may have changed
        for slug in ("n8n", "mcp"):
            if slug in self.connectors:
                await self._sync_tools(session, workspace_id, self.connectors[slug])

    async def run_health_checks(self, session: AsyncSession, workspace_id: str) -> None:
        from cockpit.workspace import allowed_roots_for

        roots = await allowed_roots_for(workspace_id)
        for slug, connector in self.connectors.items():
            ctx = ExecutionContext(
                workspace_id=workspace_id,
                run_id="health",
                correlation_id="health",
                roots=roots,
                config=getattr(connector, "runtime_config", {}) or {},
                settings=self.settings,
            )
            try:
                status: HealthStatus = await connector.health_check(ctx)
            except Exception as exc:  # a broken connector must not break the loop
                status = HealthStatus(
                    ConnectorHealthState.UNAVAILABLE, f"health check crashed: {exc}"
                )
            row = await session.scalar(
                select(Connector).where(
                    Connector.workspace_id == workspace_id, Connector.slug == slug
                )
            )
            if row is not None:
                row.health = status.state.value
                row.health_detail = status.detail
                if status.state in (ConnectorHealthState.OK, ConnectorHealthState.MOCK):
                    row.last_success_at = utcnow()
        await session.flush()


_registry: Registry | None = None


def get_registry() -> Registry:
    global _registry
    if _registry is None:
        from cockpit.config import get_settings

        _registry = Registry(get_settings())
        _registry.load()
    return _registry


def reset_registry() -> None:
    global _registry
    _registry = None
