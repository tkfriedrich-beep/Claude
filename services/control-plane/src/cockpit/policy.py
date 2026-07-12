"""Policy & Approval Gateway — deterministic permission evaluation.

Claude reasons; this module governs. No prompt, retrieved document, or connector response can
change the outcome of evaluate(): its inputs are typed state owned by the control plane.
Ordering matters and is part of the contract (tested in tests/test_policy.py):

  1. kill switch                          → deny
  2. domain disabled                      → deny
  3. connector disabled / tool disabled   → deny
  4. tool not in skill allowlist          → deny
  5. explicit deny rule                   → deny
  6. read-only connector vs write tool    → deny
  7. reads (R0/R1)                        → allow (confirm rule may force approval)
  8. Safe Mode vs external side effects   → deny
  9. exec mode read_only vs write         → deny
 10. exec mode draft / shadow             → dry-run downgrade or deny
 11. autonomy ladder                      → allow | require_approval | deny
 12. R4                                   → deny unless an explicit confirm rule → approval
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from cockpit.enums import Autonomy, ConnectorMode, ExecMode, PolicyKind, RiskLevel, ToolAccess


class Outcome(StrEnum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


@dataclass(frozen=True)
class ToolSpec:
    """The policy-relevant slice of a tool manifest."""

    tool_id: str
    connector_slug: str
    access: ToolAccess
    risk_level: RiskLevel
    external_side_effects: bool
    supports_dry_run: bool
    idempotent: bool
    enabled: bool = True
    # False for tools whose classification is supplied at *runtime registration* (n8n
    # webhooks, discovered MCP tools). Registering a connector is not a grant of trust, so we
    # never let such a tool's own "this is a read" claim earn auto-execution — see evaluate().
    trusted: bool = True


@dataclass(frozen=True)
class Rule:
    kind: PolicyKind
    tool_id: str | None = None
    connector_slug: str | None = None
    skill_slug: str | None = None
    enabled: bool = True

    def matches(self, tool: ToolSpec, skill_slug: str | None) -> bool:
        if not self.enabled:
            return False
        if self.tool_id and self.tool_id != tool.tool_id:
            return False
        if self.connector_slug and self.connector_slug != tool.connector_slug:
            return False
        if self.skill_slug and self.skill_slug != (skill_slug or ""):
            return False
        return bool(self.tool_id or self.connector_slug or self.skill_slug)


@dataclass(frozen=True)
class PolicyContext:
    safe_mode: bool
    kill_switch: bool
    exec_mode: ExecMode
    shadow: bool
    autonomy: Autonomy
    skill_slug: str | None
    skill_allowlist: frozenset[str]  # tool ids the skill manifest permits
    domain_enabled: bool
    connector_enabled: bool
    connector_mode: ConnectorMode
    rules: tuple[Rule, ...] = ()


@dataclass(frozen=True)
class Decision:
    outcome: Outcome
    reason: str
    risk_level: RiskLevel
    forced_dry_run: bool = False
    confirm_phrase_required: bool = False
    notes: tuple[str, ...] = field(default=())


def evaluate(tool: ToolSpec, ctx: PolicyContext) -> Decision:
    risk = tool.risk_level

    def deny(reason: str) -> Decision:
        return Decision(Outcome.DENY, reason, risk)

    # 1–4: hard gates
    if ctx.kill_switch:
        return deny("Kill switch is engaged — nothing executes until it is released.")
    if not ctx.domain_enabled:
        return deny("The domain for this run is disabled.")
    if not ctx.connector_enabled:
        return deny(f"Connector “{tool.connector_slug}” is disabled.")
    if not tool.enabled:
        return deny(f"Tool “{tool.tool_id}” is disabled.")
    if ctx.skill_allowlist and tool.tool_id not in ctx.skill_allowlist:
        return deny(f"Tool “{tool.tool_id}” is not in this skill's allowlist.")

    # 5: explicit deny rules beat everything below
    for rule in ctx.rules:
        if rule.kind is PolicyKind.DENY and rule.matches(tool, ctx.skill_slug):
            return deny(f"Blocked by policy rule ({rule.tool_id or rule.connector_slug}).")

    is_write = tool.access is not ToolAccess.READ
    # 6: connector-level read-only toggle
    if is_write and ctx.connector_mode is ConnectorMode.READ_ONLY:
        return deny(f"Connector “{tool.connector_slug}” is set to read-only.")

    # 7: reads run automatically within the active context (R0/R1) — but a tool from a
    # user-registered connector is untrusted: we don't believe its self-declared "read"
    # classification enough to auto-run it, because it could actually mutate an external
    # system. It needs approval (or an explicit allow rule created in the policy editor).
    if not is_write:
        if tool.external_side_effects and not tool.trusted:
            for rule in ctx.rules:
                if rule.kind is PolicyKind.ALLOW and rule.matches(tool, ctx.skill_slug):
                    return Decision(
                        Outcome.ALLOW,
                        f"Allowed by your policy rule for {rule.tool_id or rule.connector_slug}.",
                        risk,
                        notes=("allowlist", "untrusted"),
                    )
            if ctx.safe_mode:
                return deny(
                    "Safe Mode is on — a user-registered connector's external call is blocked."
                )
            return Decision(
                Outcome.REQUIRE_APPROVAL,
                "External call from a connector you registered — approve it, or add an "
                "allow rule in Settings → Policies to trust it.",
                risk,
            )
        for rule in ctx.rules:
            if rule.kind is PolicyKind.CONFIRM and rule.matches(tool, ctx.skill_slug):
                return Decision(
                    Outcome.REQUIRE_APPROVAL,
                    "A policy rule requires confirmation for this read.",
                    risk,
                )
        if ctx.autonomy is Autonomy.OFF:
            return deny("This skill's autonomy is set to Off.")
        return Decision(Outcome.ALLOW, "Read-only within the active context.", risk)

    # --- writes from here on ---
    if tool.access is ToolAccess.DESTRUCTIVE and risk is not RiskLevel.R4:
        # manifests must classify destructive as R4; treat mismatch as R4 defensively
        risk = RiskLevel.R4

    # 8: Safe Mode blocks anything with external side effects
    if ctx.safe_mode and tool.external_side_effects:
        return deny("Safe Mode is on — external changes are blocked.")

    # 9: read-only run mode
    if ctx.exec_mode is ExecMode.READ_ONLY:
        return deny("This run is in read-only mode.")

    effective_mode = ExecMode.DRAFT if ctx.shadow else ctx.exec_mode

    # 10: draft mode (and shadow runs) never execute external effects
    if effective_mode is ExecMode.DRAFT:
        if not tool.external_side_effects and risk in (RiskLevel.R2,):
            return Decision(
                Outcome.ALLOW,
                "Local reversible write allowed in draft mode.",
                risk,
                notes=("draft",),
            )
        if tool.supports_dry_run:
            return Decision(
                Outcome.ALLOW,
                "Draft/shadow mode — running as a dry-run preview, nothing will change.",
                risk,
                forced_dry_run=True,
            )
        return deny("Draft/shadow mode — this tool has no dry-run preview, so it cannot run.")

    # 11: act mode, gated by graduated autonomy
    if ctx.autonomy in (Autonomy.OFF,):
        return deny("This skill's autonomy is set to Off.")
    if ctx.autonomy in (Autonomy.OBSERVE, Autonomy.RECOMMEND):
        return deny(
            f"Autonomy is “{ctx.autonomy.label}” — writes are not permitted. "
            "Raise the skill's autonomy to Draft or higher."
        )

    if risk is RiskLevel.R4:
        # 12: disabled by default; a deliberate confirm rule enables double-confirmation
        for rule in ctx.rules:
            if rule.kind is PolicyKind.CONFIRM and rule.matches(tool, ctx.skill_slug):
                return Decision(
                    Outcome.REQUIRE_APPROVAL,
                    "High-impact action — requires typed double confirmation.",
                    risk,
                    confirm_phrase_required=True,
                )
        return deny(
            "High-impact (R4) actions are disabled. Enable them deliberately in the policy "
            "editor if you truly need this."
        )

    if ctx.autonomy is Autonomy.DRAFT:
        if not tool.external_side_effects and risk is RiskLevel.R2:
            return Decision(Outcome.ALLOW, "Local reversible write within Draft autonomy.", risk)
        if tool.supports_dry_run:
            return Decision(
                Outcome.ALLOW,
                "Draft autonomy — external action downgraded to a dry-run preview.",
                risk,
                forced_dry_run=True,
            )
        return deny("Draft autonomy — external actions require Act with approval.")

    # R2 local writes may run automatically at act autonomy; R3 needs a human (or allowlist)
    if risk is RiskLevel.R2 and not tool.external_side_effects:
        return Decision(Outcome.ALLOW, "Local reversible write.", risk)

    if ctx.autonomy is Autonomy.ACT_ALLOWLIST:
        for rule in ctx.rules:
            if rule.kind is PolicyKind.ALLOW and rule.matches(tool, ctx.skill_slug):
                return Decision(
                    Outcome.ALLOW,
                    f"Allowed by your policy rule for {rule.tool_id or rule.connector_slug}.",
                    risk,
                    notes=("allowlist",),
                )
        return Decision(
            Outcome.REQUIRE_APPROVAL,
            "No allowlist rule covers this action — asking for approval.",
            risk,
        )

    return Decision(
        Outcome.REQUIRE_APPROVAL,
        "External change — needs your explicit approval before it runs.",
        risk,
    )
