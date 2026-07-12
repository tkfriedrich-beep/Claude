"""Deterministic policy matrix — the security contract (THREAT_MODEL §invariants)."""

from __future__ import annotations

from cockpit.enums import Autonomy, ConnectorMode, ExecMode, PolicyKind, RiskLevel, ToolAccess
from cockpit.policy import Outcome, PolicyContext, Rule, ToolSpec, evaluate


def spec(**kw) -> ToolSpec:
    defaults = dict(
        tool_id="t.read",
        connector_slug="c",
        access=ToolAccess.READ,
        risk_level=RiskLevel.R0,
        external_side_effects=False,
        supports_dry_run=False,
        idempotent=True,
    )
    defaults.update(kw)
    return ToolSpec(**defaults)


def ctx(**kw) -> PolicyContext:
    defaults = dict(
        safe_mode=False,
        kill_switch=False,
        exec_mode=ExecMode.ACT,
        shadow=False,
        autonomy=Autonomy.ACT_WITH_APPROVAL,
        skill_slug="s",
        skill_allowlist=frozenset(),
        domain_enabled=True,
        connector_enabled=True,
        connector_mode=ConnectorMode.READ_WRITE,
        rules=(),
    )
    defaults.update(kw)
    return PolicyContext(**defaults)


WRITE_R3 = dict(
    tool_id="t.write",
    access=ToolAccess.WRITE,
    risk_level=RiskLevel.R3,
    external_side_effects=True,
    supports_dry_run=True,
)


def test_kill_switch_denies_everything() -> None:
    assert evaluate(spec(), ctx(kill_switch=True)).outcome is Outcome.DENY


def test_disabled_domain_denies() -> None:
    assert evaluate(spec(), ctx(domain_enabled=False)).outcome is Outcome.DENY


def test_disabled_connector_denies() -> None:
    assert evaluate(spec(), ctx(connector_enabled=False)).outcome is Outcome.DENY


def test_tool_outside_skill_allowlist_denies() -> None:
    decision = evaluate(spec(), ctx(skill_allowlist=frozenset({"other.tool"})))
    assert decision.outcome is Outcome.DENY
    assert "allowlist" in decision.reason


def test_reads_allowed_within_context() -> None:
    assert evaluate(spec(), ctx()).outcome is Outcome.ALLOW
    assert evaluate(spec(risk_level=RiskLevel.R1), ctx(safe_mode=True)).outcome is Outcome.ALLOW


def test_safe_mode_blocks_external_writes_even_with_high_autonomy() -> None:
    decision = evaluate(spec(**WRITE_R3), ctx(safe_mode=True, autonomy=Autonomy.ACT_ALLOWLIST))
    assert decision.outcome is Outcome.DENY
    assert "Safe Mode" in decision.reason


def test_read_only_mode_blocks_writes() -> None:
    decision = evaluate(spec(**WRITE_R3), ctx(exec_mode=ExecMode.READ_ONLY))
    assert decision.outcome is Outcome.DENY


def test_read_only_connector_blocks_writes() -> None:
    decision = evaluate(spec(**WRITE_R3), ctx(connector_mode=ConnectorMode.READ_ONLY))
    assert decision.outcome is Outcome.DENY


def test_draft_mode_downgrades_external_write_to_dry_run() -> None:
    decision = evaluate(spec(**WRITE_R3), ctx(exec_mode=ExecMode.DRAFT))
    assert decision.outcome is Outcome.ALLOW
    assert decision.forced_dry_run is True


def test_draft_mode_denies_external_write_without_dry_run() -> None:
    decision = evaluate(
        spec(**{**WRITE_R3, "supports_dry_run": False}), ctx(exec_mode=ExecMode.DRAFT)
    )
    assert decision.outcome is Outcome.DENY


def test_shadow_forces_draft_semantics_even_in_act_mode() -> None:
    decision = evaluate(spec(**WRITE_R3), ctx(shadow=True, exec_mode=ExecMode.ACT))
    assert decision.outcome is Outcome.ALLOW
    assert decision.forced_dry_run is True


def test_observe_autonomy_blocks_writes() -> None:
    for autonomy in (Autonomy.OBSERVE, Autonomy.RECOMMEND):
        decision = evaluate(spec(**WRITE_R3), ctx(autonomy=autonomy))
        assert decision.outcome is Outcome.DENY


def test_act_with_approval_requires_approval_for_r3() -> None:
    decision = evaluate(spec(**WRITE_R3), ctx(autonomy=Autonomy.ACT_WITH_APPROVAL))
    assert decision.outcome is Outcome.REQUIRE_APPROVAL


def test_local_r2_write_allowed_at_act_autonomy() -> None:
    decision = evaluate(
        spec(tool_id="t.local", access=ToolAccess.WRITE, risk_level=RiskLevel.R2),
        ctx(autonomy=Autonomy.ACT_WITH_APPROVAL),
    )
    assert decision.outcome is Outcome.ALLOW


def test_allowlist_autonomy_needs_matching_rule() -> None:
    no_rule = evaluate(spec(**WRITE_R3), ctx(autonomy=Autonomy.ACT_ALLOWLIST))
    assert no_rule.outcome is Outcome.REQUIRE_APPROVAL
    with_rule = evaluate(
        spec(**WRITE_R3),
        ctx(
            autonomy=Autonomy.ACT_ALLOWLIST, rules=(Rule(kind=PolicyKind.ALLOW, tool_id="t.write"),)
        ),
    )
    assert with_rule.outcome is Outcome.ALLOW


def test_deny_rule_beats_allowlist() -> None:
    decision = evaluate(
        spec(**WRITE_R3),
        ctx(
            autonomy=Autonomy.ACT_ALLOWLIST,
            rules=(
                Rule(kind=PolicyKind.DENY, tool_id="t.write"),
                Rule(kind=PolicyKind.ALLOW, tool_id="t.write"),
            ),
        ),
    )
    assert decision.outcome is Outcome.DENY


def test_r4_denied_by_default() -> None:
    decision = evaluate(
        spec(
            tool_id="t.nuke",
            access=ToolAccess.DESTRUCTIVE,
            risk_level=RiskLevel.R4,
            external_side_effects=True,
        ),
        ctx(autonomy=Autonomy.ACT_ALLOWLIST),
    )
    assert decision.outcome is Outcome.DENY


def test_r4_with_confirm_rule_requires_typed_confirmation() -> None:
    decision = evaluate(
        spec(
            tool_id="t.nuke",
            access=ToolAccess.DESTRUCTIVE,
            risk_level=RiskLevel.R4,
            external_side_effects=True,
        ),
        ctx(rules=(Rule(kind=PolicyKind.CONFIRM, tool_id="t.nuke"),)),
    )
    assert decision.outcome is Outcome.REQUIRE_APPROVAL
    assert decision.confirm_phrase_required is True


def test_destructive_access_is_treated_as_r4_even_if_misclassified() -> None:
    decision = evaluate(
        spec(
            tool_id="t.rm",
            access=ToolAccess.DESTRUCTIVE,
            risk_level=RiskLevel.R2,
            external_side_effects=True,
        ),
        ctx(autonomy=Autonomy.ACT_WITH_APPROVAL),
    )
    assert decision.outcome is Outcome.DENY  # defensive upgrade to R4 path
