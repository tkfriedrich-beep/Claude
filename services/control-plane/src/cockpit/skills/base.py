"""Skill executor contract.

Executors must be deterministic given (input, sources): resumed runs re-enter execute() from
the top and rely on the gateway's idempotent replay for already-completed tool calls (ADR/
gateway docstring). All side effects go through ctx.call_tool — never direct I/O.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from cockpit.config import Settings
from cockpit.connectors.base import ToolResult
from cockpit.enums import EventType
from cockpit.events import EventBus
from cockpit.gateway import ToolGateway
from cockpit.models import Run
from cockpit.workspace import WorkspaceSettings


class SkillFailure(Exception):
    """Expected failure with a human-readable reason (budget, denial of an essential step…)."""


class RunCancelled(Exception):
    """The user cancelled the run while it was executing; stop cleanly."""


@dataclass
class ArtifactSpec:
    kind: str  # markdown|json|text|diff
    title: str
    filename: str
    content: str
    mime: str = "text/markdown"
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryProposal:
    kind: str
    content: str
    rationale: str
    structured: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.6
    domain_key: str | None = None
    sources: list[dict[str, str]] = field(default_factory=list)  # {source_type, reference, excerpt}


@dataclass
class SkillResult:
    summary_md: str
    data: dict[str, Any] = field(default_factory=dict)
    artifacts: list[ArtifactSpec] = field(default_factory=list)
    sources: list[dict[str, str]] = field(default_factory=list)  # {label, reference}
    unresolved: list[str] = field(default_factory=list)
    memory_proposals: list[MemoryProposal] = field(default_factory=list)
    generation_mode: str = "deterministic"  # deterministic | llm_assisted


@dataclass
class Plan:
    steps: list[str]
    expected_tools: list[str] = field(default_factory=list)
    side_effects_expected: bool = False
    success_checks: list[str] = field(default_factory=list)
    assumption: str | None = None  # displayed reversible assumption (loop step 2)


class SkillContext:
    def __init__(
        self,
        *,
        session: AsyncSession,
        run: Run,
        gateway: ToolGateway,
        bus: EventBus,
        settings: Settings,
        ws: WorkspaceSettings,
        manifest: dict[str, Any],
        generate: Callable[[str], Awaitable[str | None]] | None = None,
    ) -> None:
        self.session = session
        self.run = run
        self.gateway = gateway
        self.bus = bus
        self.settings = settings
        self.ws = ws
        self.manifest = manifest
        self._generate = generate

    @property
    def input(self) -> dict[str, Any]:
        return self.run.input or {}

    @property
    def demo_mode(self) -> bool:
        return self.ws.demo_mode

    async def call_tool(
        self, tool_id: str, tool_input: dict[str, Any], *, purpose: str, why: str = ""
    ) -> ToolResult:
        # Honor a cancel issued from the API while we were executing (cheap committed-state read).
        await self.session.refresh(self.run, attribute_names=["status"])
        if self.run.status == "cancelled":
            raise RunCancelled("Cancelled by you.")
        max_steps = int(self.manifest.get("max_steps", self.settings.max_steps_default))
        if self.run.steps >= max_steps:
            raise SkillFailure(
                f"Step budget exhausted ({max_steps} tool calls) — stopping for safety."
            )
        return await self.gateway.call_tool(
            self.session, self.run, tool_id, tool_input, purpose=purpose, why=why
        )

    async def progress(self, message: str) -> None:
        await self.bus.emit(
            self.session,
            workspace_id=self.run.workspace_id,
            run_id=self.run.id,
            type=EventType.TOOL_PROGRESS,
            payload={"message": message},
        )

    async def generate(self, prompt: str) -> str | None:
        """LLM text enrichment — None when no provider is healthy (deterministic fallback)."""
        if self._generate is None:
            return None
        return await self._generate(prompt)


class BaseSkillExecutor:
    slug: str = ""

    def __init__(self, ctx: SkillContext) -> None:
        self.ctx = ctx

    async def plan(self) -> Plan:
        raise NotImplementedError

    async def execute(self) -> SkillResult:
        raise NotImplementedError
