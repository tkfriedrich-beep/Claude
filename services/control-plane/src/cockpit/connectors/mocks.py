"""Mock connectors for services that are scaffolded but not genuinely configured.

Every payload these return carries `"demo": true`, and the connectors report health "mock" —
the UI labels them honestly. calendar.create_event exists to exercise the R3 external-write
approval path end-to-end without touching a real calendar.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cockpit.connectors.base import (
    BaseConnector,
    ConnectorError,
    ExecutionContext,
    HealthStatus,
    PreviewNotSupported,
    ToolResult,
)
from cockpit.enums import ConnectorHealthState


def _load_demo_json(ctx: ExecutionContext, name: str) -> Any:
    path = Path(ctx.settings.demo_dir) / name if ctx.settings else None
    if path is None or not path.exists():
        raise ConnectorError(f"Demo data file missing: {name}")
    return json.loads(path.read_text(encoding="utf-8"))


class GoogleWorkspaceMockConnector(BaseConnector):
    slug = "google-workspace"

    def __init__(self, manifest_dir: Path) -> None:
        super().__init__(manifest_dir)
        self._created_events: list[dict[str, Any]] = []

    async def health_check(self, ctx: ExecutionContext) -> HealthStatus:
        return HealthStatus(
            ConnectorHealthState.MOCK,
            "Mock — not connected to a real Google account. Data shown is demo data.",
        )

    async def preview(
        self, tool_id: str, validated_input: dict[str, Any], ctx: ExecutionContext
    ) -> ToolResult:
        if tool_id == "google.calendar.create_event":
            return ToolResult(
                ok=True,
                data={
                    "created": False,
                    "demo": True,
                    "diff": f"+ {validated_input.get('title')} at {validated_input.get('start')}",
                },
                summary="Preview: would create calendar event (demo)",
            )
        raise PreviewNotSupported(f"{tool_id} has no preview")

    async def execute(
        self, tool_id: str, validated_input: dict[str, Any], ctx: ExecutionContext
    ) -> ToolResult:
        match tool_id:
            case "google.calendar.list_events":
                events = _load_demo_json(ctx, "agenda.json")["events"]
                events = events + [e for e in self._created_events]
                return ToolResult(
                    ok=True,
                    data={"events": events, "demo": True},
                    summary=f"Fetched {len(events)} calendar events (demo data)",
                )
            case "google.calendar.create_event":
                assert not ctx.dry_run, "real create_event called for a dry-run"
                event = {
                    **validated_input,
                    "id": f"demo-evt-{len(self._created_events) + 1}",
                    "demo": True,
                }
                self._created_events.append(event)
                return ToolResult(
                    ok=True,
                    data={"created": True, "event": event, "demo": True},
                    summary=f"Created demo calendar event “{validated_input.get('title')}”",
                    external_confirmed=True,  # confirmed by the mock backend
                )
            case "google.gmail.search":
                messages = _load_demo_json(ctx, "emails.json")["messages"]
                q = validated_input.get("query", "").lower()
                hits = [m for m in messages if q in json.dumps(m).lower()] if q else messages
                return ToolResult(
                    ok=True,
                    data={"messages": hits[:20], "demo": True},
                    summary=f"Found {len(hits)} demo emails",
                )
        raise ConnectorError(f"unknown tool {tool_id}")


class NotionMockConnector(BaseConnector):
    slug = "notion"

    async def health_check(self, ctx: ExecutionContext) -> HealthStatus:
        return HealthStatus(
            ConnectorHealthState.MOCK,
            "Mock — connect a real Notion integration to replace demo data.",
        )

    async def execute(
        self, tool_id: str, validated_input: dict[str, Any], ctx: ExecutionContext
    ) -> ToolResult:
        if tool_id == "notion.search_pages":
            pages = _load_demo_json(ctx, "notion_pages.json")["pages"]
            q = validated_input.get("query", "").lower()
            hits = [p for p in pages if q in json.dumps(p).lower()] if q else pages
            return ToolResult(
                ok=True,
                data={"pages": hits[:20], "demo": True},
                summary=f"Found {len(hits)} demo Notion pages",
            )
        raise ConnectorError(f"unknown tool {tool_id}")


class GitHubMockConnector(BaseConnector):
    slug = "github"

    async def health_check(self, ctx: ExecutionContext) -> HealthStatus:
        return HealthStatus(
            ConnectorHealthState.MOCK,
            "Mock — connect a real GitHub account to replace demo data.",
        )

    async def execute(
        self, tool_id: str, validated_input: dict[str, Any], ctx: ExecutionContext
    ) -> ToolResult:
        if tool_id == "github.list_issues":
            issues = _load_demo_json(ctx, "github_issues.json")["issues"]
            return ToolResult(
                ok=True,
                data={"issues": issues[:30], "demo": True},
                summary=f"Fetched {len(issues)} demo GitHub issues",
            )
        raise ConnectorError(f"unknown tool {tool_id}")
