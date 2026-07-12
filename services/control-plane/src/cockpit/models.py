"""SQLAlchemy models. Every table carries workspace_id (single-user MVP, multi-user ready).

Rules:
- run.status is written only by cockpit.state_machine.transition().
- JSON payload columns store *redacted* data only (see logging.redact).
- Secrets never appear here; connectors store secret *names*, resolved via SecretStore.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """SQLite drops tzinfo; store UTC, re-attach UTC on load so comparisons stay aware."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is not None and value.tzinfo is not None:
            return value.astimezone(UTC)
        return value

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}  # noqa: RUF012


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class Workspace(Base, TimestampMixin):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="Personal")
    # Operational switches + preferences. Not secrets.
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class UserProfile(Base, TimestampMixin):
    __tablename__ = "user_profiles"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    user_name: Mapped[str] = mapped_column(String(120))
    assistant_name: Mapped[str] = mapped_column(String(120), default="Otto")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    onboarded_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Domain(Base, TimestampMixin):
    __tablename__ = "domains"
    __table_args__ = (UniqueConstraint("workspace_id", "key"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    key: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    read_only: Mapped[bool] = mapped_column(Boolean, default=False)
    sensitivity: Mapped[str] = mapped_column(String(20), default="normal")


class Project(Base, TimestampMixin):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(200), index=True)
    status: Mapped[str] = mapped_column(String(40), default="active")
    domain_key: Mapped[str] = mapped_column(String(40), default="work")
    path: Mapped[str | None] = mapped_column(String(1024))  # vault-relative source path
    description: Mapped[str] = mapped_column(Text, default="")


class Person(Base, TimestampMixin):
    __tablename__ = "people"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    relation: Mapped[str] = mapped_column(String(120), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    source_ref: Mapped[str | None] = mapped_column(String(1024))


class Commitment(Base, TimestampMixin):
    __tablename__ = "commitments"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    title: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|done|dropped
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    source_ref: Mapped[str | None] = mapped_column(String(1024))


class AgentProfile(Base, TimestampMixin):
    __tablename__ = "agent_profiles"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), default="Otto")
    provider: Mapped[str] = mapped_column(String(40), default="mock")  # claude|mock|openai|...
    system_prompt_version: Mapped[str] = mapped_column(String(40), default="otto_v1")
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ProviderSession(Base, TimestampMixin):
    __tablename__ = "provider_sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    agent_profile_id: Mapped[str | None] = mapped_column(ForeignKey("agent_profiles.id"))
    provider: Mapped[str] = mapped_column(String(40))
    # External/provider session id is stored separately from our internal id on purpose.
    external_session_id: Mapped[str | None] = mapped_column(String(200), index=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    title: Mapped[str] = mapped_column(String(300), default="New session")
    last_active_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Skill(Base, TimestampMixin):
    __tablename__ = "skills"
    __table_args__ = (UniqueConstraint("workspace_id", "slug"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    slug: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[str] = mapped_column(String(40), default="0.1.0")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    autonomy: Mapped[int] = mapped_column(Integer, default=3)
    risk_level: Mapped[str] = mapped_column(String(4), default="R2")
    domains: Mapped[list[Any]] = mapped_column(JSON, default=list)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class SkillVersion(Base, TimestampMixin):
    __tablename__ = "skill_versions"
    __table_args__ = (UniqueConstraint("workspace_id", "skill_slug", "version"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    skill_slug: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[str] = mapped_column(String(40))
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Connector(Base, TimestampMixin):
    __tablename__ = "connectors"
    __table_args__ = (UniqueConstraint("workspace_id", "slug"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    slug: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(60), default="local")
    mode: Mapped[str] = mapped_column(String(20), default="read_only")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    health: Mapped[str] = mapped_column(String(20), default="unknown")
    health_detail: Mapped[str] = mapped_column(Text, default="")
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # non-secret config only


class ConnectorTool(Base, TimestampMixin):
    __tablename__ = "connector_tools"
    __table_args__ = (UniqueConstraint("workspace_id", "tool_id"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    connector_slug: Mapped[str] = mapped_column(String(120), index=True)
    tool_id: Mapped[str] = mapped_column(String(200), index=True)
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[str] = mapped_column(String(40), default="1")
    access: Mapped[str] = mapped_column(String(20), default="read")
    risk_level: Mapped[str] = mapped_column(String(4), default="R0")
    external_side_effects: Mapped[bool] = mapped_column(Boolean, default=False)
    # False for runtime-registered tools (n8n/MCP) — always require approval, never auto-run.
    trusted: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class PolicyRule(Base, TimestampMixin):
    __tablename__ = "policies"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20))  # allow|deny|confirm
    tool_id: Mapped[str | None] = mapped_column(String(200), index=True)
    connector_slug: Mapped[str | None] = mapped_column(String(120))
    skill_slug: Mapped[str | None] = mapped_column(String(120))
    condition: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str] = mapped_column(Text, default="")


class Schedule(Base, TimestampMixin):
    __tablename__ = "schedules"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    skill_slug: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(200))
    interval_minutes: Mapped[int] = mapped_column(Integer, default=1440)
    next_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_run_status: Mapped[str | None] = mapped_column(String(20))
    last_run_id: Mapped[str | None] = mapped_column(String(64))
    shadow_mode: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    input: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Run(Base, TimestampMixin):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="skill")
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    title: Mapped[str] = mapped_column(String(300), default="Run")
    skill_slug: Mapped[str | None] = mapped_column(String(120), index=True)
    session_id: Mapped[str | None] = mapped_column(ForeignKey("provider_sessions.id"), index=True)
    schedule_id: Mapped[str | None] = mapped_column(String(64))
    command_text: Mapped[str] = mapped_column(Text, default="")
    input: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    mode: Mapped[str] = mapped_column(String(20), default="draft")
    shadow: Mapped[bool] = mapped_column(Boolean, default=False)
    domain_key: Mapped[str | None] = mapped_column(String(40))
    context_pack_id: Mapped[str | None] = mapped_column(String(64))
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    verification: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    review: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    status_reason: Mapped[str | None] = mapped_column(String(300))
    budget_usd: Mapped[float | None] = mapped_column(Float)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    steps: Mapped[int] = mapped_column(Integer, default=0)
    provider: Mapped[str | None] = mapped_column(String(40))
    worker_claim: Mapped[str | None] = mapped_column(String(64))
    heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    approval_wait_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    scheduled_for: Mapped[datetime | None] = mapped_column(UTCDateTime())


Index("ix_runs_claimable", Run.status, Run.scheduled_for)


class RunEvent(Base):
    __tablename__ = "run_events"
    # Global autoincrement id doubles as the SSE cursor (Last-Event-ID / ?since=).
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)  # monotonic per run
    type: Mapped[str] = mapped_column(String(60), index=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    human_text: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # redacted


class ToolCall(Base, TimestampMixin):
    __tablename__ = "tool_calls"
    __table_args__ = (UniqueConstraint("workspace_id", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    tool_id: Mapped[str] = mapped_column(String(200), index=True)
    connector_slug: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    risk_level: Mapped[str] = mapped_column(String(4), default="R0")
    purpose: Mapped[str] = mapped_column(String(500), default="")
    input: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # redacted
    # User-authored replacement input from an approval "edit" — intentionally raw, since the
    # user typed it for execution; never sourced from retrieved content.
    edited_input: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # redacted
    error: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(80))
    external_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class Approval(Base, TimestampMixin):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    tool_call_id: Mapped[str | None] = mapped_column(ForeignKey("tool_calls.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    title: Mapped[str] = mapped_column(String(300))
    what: Mapped[str] = mapped_column(Text, default="")
    why: Mapped[str] = mapped_column(Text, default="")
    target: Mapped[str] = mapped_column(String(300), default="")
    data_preview: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # redacted
    diff_preview: Mapped[str | None] = mapped_column(Text)
    risk_level: Mapped[str] = mapped_column(String(4), default="R3")
    reversibility: Mapped[str] = mapped_column(String(300), default="")
    cost_estimate: Mapped[str | None] = mapped_column(String(120))
    confirm_phrase_required: Mapped[bool] = mapped_column(Boolean, default=False)
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    decision_note: Mapped[str] = mapped_column(Text, default="")
    resolved_by: Mapped[str | None] = mapped_column(String(120))


class Artifact(Base, TimestampMixin):
    __tablename__ = "artifacts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    skill_slug: Mapped[str | None] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20), default="markdown")
    title: Mapped[str] = mapped_column(String(300))
    path: Mapped[str] = mapped_column(String(1024))  # relative to artifacts dir
    mime: Mapped[str] = mapped_column(String(100), default="text/markdown")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Memory(Base, TimestampMixin):
    __tablename__ = "memories"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30), default="working")
    status: Mapped[str] = mapped_column(String(20), default="proposed", index=True)
    content: Mapped[str] = mapped_column(Text)
    structured: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.6)
    sensitivity: Mapped[str] = mapped_column(String(20), default="normal")
    domain_key: Mapped[str | None] = mapped_column(String(40))
    rationale: Mapped[str] = mapped_column(Text, default="")  # user-visible: why saved
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class MemorySource(Base, TimestampMixin):
    __tablename__ = "memory_sources"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    memory_id: Mapped[str] = mapped_column(ForeignKey("memories.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(30), default="file")  # file|run|chat|manual
    reference: Mapped[str] = mapped_column(String(1024))
    excerpt: Mapped[str] = mapped_column(Text, default="")


class ContextPack(Base, TimestampMixin):
    __tablename__ = "context_packs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    domain_key: Mapped[str | None] = mapped_column(String(40))
    sources: Mapped[list[Any]] = mapped_column(JSON, default=list)
    instructions: Mapped[str] = mapped_column(Text, default="")
