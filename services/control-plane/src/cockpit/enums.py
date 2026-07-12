"""Shared enums. String values are part of the API contract — change only with a migration."""

from __future__ import annotations

from enum import IntEnum, StrEnum


class RunStatus(StrEnum):
    QUEUED = "queued"
    TRIAGING = "triaging"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


TERMINAL_STATUSES = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}


class RunKind(StrEnum):
    SKILL = "skill"
    CHAT = "chat"


class ExecMode(StrEnum):
    READ_ONLY = "read_only"
    DRAFT = "draft"
    ACT = "act"


class RiskLevel(StrEnum):
    R0 = "R0"  # local read-only
    R1 = "R1"  # external read-only
    R2 = "R2"  # draft or local reversible write
    R3 = "R3"  # external reversible write
    R4 = "R4"  # destructive / financial / legal / health / identity / broadcast

    @property
    def rank(self) -> int:
        return int(self.value[1])


class Autonomy(IntEnum):
    OFF = 0
    OBSERVE = 1
    RECOMMEND = 2
    DRAFT = 3
    ACT_WITH_APPROVAL = 4
    ACT_ALLOWLIST = 5

    @property
    def label(self) -> str:
        return {
            0: "Off",
            1: "Observe",
            2: "Recommend",
            3: "Draft",
            4: "Act with approval",
            5: "Act within allowlist",
        }[int(self)]


class ToolAccess(StrEnum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ToolCallStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    DENIED = "denied"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ConnectorMode(StrEnum):
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"


class ConnectorHealthState(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"
    MOCK = "mock"


class ArtifactKind(StrEnum):
    MARKDOWN = "markdown"
    JSON = "json"
    TEXT = "text"
    DIFF = "diff"


class MemoryStatus(StrEnum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    REJECTED = "rejected"
    EXPIRED = "expired"


class MemoryKind(StrEnum):
    PROFILE = "profile"
    PERSON = "person"
    PROJECT = "project"
    COMMITMENT = "commitment"
    DECISION = "decision"
    PROCEDURE = "procedure"
    WORKING = "working"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"
    ERROR = "error"


class EventType(StrEnum):
    RUN_QUEUED = "run.queued"
    RUN_STARTED = "run.started"
    AGENT_STATUS_CHANGED = "agent.status_changed"
    ASSISTANT_MESSAGE_DELTA = "assistant.message_delta"
    PLAN_CREATED = "plan.created"
    TOOL_PROPOSED = "tool.proposed"
    APPROVAL_REQUIRED = "approval.required"
    APPROVAL_RESOLVED = "approval.resolved"
    TOOL_STARTED = "tool.started"
    TOOL_PROGRESS = "tool.progress"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"
    ARTIFACT_CREATED = "artifact.created"
    VERIFICATION_COMPLETED = "verification.completed"
    MEMORY_PROPOSED = "memory.proposed"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"


class PolicyKind(StrEnum):
    ALLOW = "allow"  # allowlist rule for autonomy level 5
    DENY = "deny"  # always deny a tool/connector
    CONFIRM = "confirm"  # enables R4 double-confirm path for a tool


DEFAULT_DOMAINS: list[dict[str, object]] = [
    {"key": "today", "name": "Today", "enabled": True, "sensitivity": "normal"},
    {"key": "work", "name": "Work", "enabled": True, "sensitivity": "normal"},
    {"key": "ventures", "name": "Ventures", "enabled": True, "sensitivity": "normal"},
    {"key": "people", "name": "People", "enabled": True, "sensitivity": "normal"},
    {"key": "knowledge", "name": "Knowledge", "enabled": True, "sensitivity": "normal"},
    {"key": "personal", "name": "Personal", "enabled": True, "sensitivity": "normal"},
    # High-sensitivity domains: scaffolded, OFF by default, read-only until explicitly enabled.
    {"key": "health", "name": "Health", "enabled": False, "sensitivity": "high"},
    {"key": "money", "name": "Money", "enabled": False, "sensitivity": "high"},
    {"key": "home", "name": "Home", "enabled": False, "sensitivity": "normal"},
    {"key": "travel", "name": "Travel", "enabled": False, "sensitivity": "normal"},
]
