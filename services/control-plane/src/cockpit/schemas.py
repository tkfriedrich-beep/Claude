"""Pydantic API schemas — the OpenAPI contract consumed by packages/contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------- requests ----------


class OnboardingRequest(BaseModel):
    user_name: str = Field(min_length=1, max_length=120)
    assistant_name: str = Field(default="Otto", max_length=120)
    timezone: str = "UTC"
    vault_path: str | None = None
    bizideas_path: str | None = None
    enable_demo_data: bool = True
    safe_mode: bool = True
    default_autonomy: int = Field(default=3, ge=0, le=5)
    provider: Literal["mock", "claude"] = "mock"


class CommandRequest(BaseModel):
    text: str = ""
    skill_slug: str | None = None
    session_id: str | None = None
    domain_key: str | None = None
    context_pack_id: str | None = None
    mode: Literal["read_only", "draft", "act"] = "draft"
    input: dict[str, Any] = Field(default_factory=dict)
    budget_usd: float | None = Field(default=None, ge=0)
    title: str | None = None


class ApprovalResolveRequest(BaseModel):
    decision: Literal["approve", "deny"]
    note: str = ""
    edited_input: dict[str, Any] | None = None
    confirm_phrase: str | None = None


class SkillPatchRequest(BaseModel):
    autonomy: int | None = Field(default=None, ge=0, le=5)
    enabled: bool | None = None


class ConnectorPatchRequest(BaseModel):
    enabled: bool | None = None
    mode: Literal["read_only", "read_write"] | None = None
    config: dict[str, Any] | None = None


class ConnectorRegisterRequest(BaseModel):
    kind: Literal["n8n_webhook", "mcp_server"]
    name: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    # n8n
    url: str | None = None
    secret_env: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    read_only: bool = False
    supports_dry_run: bool = False
    description: str = ""
    # mcp
    transport: Literal["stdio", "inproc"] | None = None
    command: str | None = None
    args: list[str] = Field(default_factory=list)


class AutomationCreateRequest(BaseModel):
    skill_slug: str
    name: str | None = None
    interval_minutes: int = Field(default=1440, ge=15)
    shadow_mode: bool = True
    input: dict[str, Any] = Field(default_factory=dict)
    start_in_minutes: int = Field(default=0, ge=0)


class AutomationPatchRequest(BaseModel):
    enabled: bool | None = None
    shadow_mode: bool | None = None
    interval_minutes: int | None = Field(default=None, ge=15)


class SettingsPatchRequest(BaseModel):
    safe_mode: bool | None = None
    kill_switch: bool | None = None
    theme: str | None = None
    default_mode: Literal["read_only", "draft", "act"] | None = None
    provider: Literal["mock", "claude"] | None = None
    vault_path: str | None = None
    bizideas_path: str | None = None
    daily_budget_usd: float | None = Field(default=None, ge=0)
    run_budget_usd: float | None = Field(default=None, ge=0)


class MemoryPatchRequest(BaseModel):
    action: Literal["approve", "reject"]
    content: str | None = None


class DomainPatchRequest(BaseModel):
    enabled: bool | None = None
    read_only: bool | None = None


class PolicyCreateRequest(BaseModel):
    name: str
    kind: Literal["allow", "deny", "confirm"]
    tool_id: str | None = None
    connector_slug: str | None = None
    skill_slug: str | None = None
    note: str = ""


# ---------- responses ----------


class RunOut(BaseModel):
    id: str
    workspace_id: str
    kind: str
    status: str
    title: str
    skill_slug: str | None
    session_id: str | None
    command_text: str
    mode: str
    shadow: bool
    plan: dict[str, Any] | None
    result: dict[str, Any] | None
    verification: dict[str, Any] | None
    review: dict[str, Any] | None
    error: str | None
    status_reason: str | None
    provider: str | None
    cost_usd: float
    tokens_in: int
    tokens_out: int
    steps: int
    correlation_id: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class EventOut(BaseModel):
    id: int
    run_id: str
    seq: int
    type: str
    ts: datetime
    human_text: str
    payload: dict[str, Any]

    model_config = {"from_attributes": True}


class ApprovalOut(BaseModel):
    id: str
    run_id: str
    tool_call_id: str | None
    status: str
    title: str
    what: str
    why: str
    target: str
    data_preview: dict[str, Any]
    diff_preview: str | None
    risk_level: str
    reversibility: str
    cost_estimate: str | None
    confirm_phrase_required: bool
    requested_at: datetime
    expires_at: datetime | None
    resolved_at: datetime | None
    decision_note: str

    model_config = {"from_attributes": True}


class SkillOut(BaseModel):
    id: str
    slug: str
    name: str
    description: str
    version: str
    enabled: bool
    autonomy: int
    risk_level: str
    domains: list[Any]
    manifest: dict[str, Any]

    model_config = {"from_attributes": True}


class ConnectorOut(BaseModel):
    id: str
    slug: str
    name: str
    category: str
    mode: str
    enabled: bool
    health: str
    health_detail: str
    last_success_at: datetime | None
    manifest: dict[str, Any]
    config: dict[str, Any]

    model_config = {"from_attributes": True}


class ConnectorToolOut(BaseModel):
    tool_id: str
    name: str
    access: str
    risk_level: str
    external_side_effects: bool
    trusted: bool
    enabled: bool

    model_config = {"from_attributes": True}


class ArtifactOut(BaseModel):
    id: str
    run_id: str
    skill_slug: str | None
    kind: str
    title: str
    path: str
    mime: str
    size_bytes: int
    meta: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class MemoryOut(BaseModel):
    id: str
    kind: str
    status: str
    content: str
    structured: dict[str, Any]
    confidence: float
    sensitivity: str
    domain_key: str | None
    rationale: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ScheduleOut(BaseModel):
    id: str
    skill_slug: str
    name: str
    interval_minutes: int
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_run_status: str | None
    last_run_id: str | None
    shadow_mode: bool
    enabled: bool

    model_config = {"from_attributes": True}


class SessionOut(BaseModel):
    id: str
    provider: str
    external_session_id: str | None
    status: str
    title: str
    last_active_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class DomainOut(BaseModel):
    key: str
    name: str
    enabled: bool
    read_only: bool
    sensitivity: str

    model_config = {"from_attributes": True}


class PolicyOut(BaseModel):
    id: str
    name: str
    kind: str
    tool_id: str | None
    connector_slug: str | None
    skill_slug: str | None
    enabled: bool
    note: str

    model_config = {"from_attributes": True}


class Problem(BaseModel):
    """RFC-9457 problem details."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    correlation_id: str | None = None
