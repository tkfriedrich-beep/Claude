"""API integration: onboarding → briefing → command → approvals → settings → doctor."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from cockpit.main import create_app


@pytest.fixture
async def client(app_env: dict) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    transport = httpx.ASGITransport(app=app)  # lifespan skipped; engine set up by app_env
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


async def onboard(client: httpx.AsyncClient) -> str:
    from tests.conftest import REPO_ROOT

    response = await client.post(
        "/api/v1/onboarding",
        json={
            "user_name": "Testa",
            "assistant_name": "Otto",
            "enable_demo_data": False,
            "safe_mode": True,
            "vault_path": str(REPO_ROOT / "data" / "demo" / "vault"),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["workspace_id"]


async def test_onboarding_status_flow(client: httpx.AsyncClient) -> None:
    before = await client.get("/api/v1/onboarding/status")
    assert before.json()["completed"] is False
    await onboard(client)
    after = await client.get("/api/v1/onboarding/status")
    assert after.json() == {**after.json(), "completed": True, "user_name": "Testa"}


async def test_briefing_requires_workspace(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/briefing")
    assert response.status_code == 409
    body = response.json()
    assert body["status"] == 409 and "onboarding" in body["detail"]


async def test_briefing_and_settings(client: httpx.AsyncClient) -> None:
    await onboard(client)
    briefing = (await client.get("/api/v1/briefing")).json()
    assert briefing["assistant_name"] == "Otto"
    assert briefing["safe_mode"] is True
    assert briefing["metrics"]["connectors_total"] == 8  # +web (Web Research)
    assert isinstance(briefing["what_matters"], list) and briefing["what_matters"]

    patch = await client.patch("/api/v1/settings", json={"safe_mode": False})
    assert patch.status_code == 200
    assert (await client.get("/api/v1/settings")).json()["safe_mode"] is False


async def test_command_creates_queued_run_with_events(client: httpx.AsyncClient) -> None:
    await onboard(client)
    response = await client.post("/api/v1/commands", json={"text": "hello"})
    assert response.status_code == 201
    run = response.json()
    assert run["status"] == "queued" and run["kind"] == "chat"
    events = (await client.get(f"/api/v1/runs/{run['id']}/events")).json()
    assert [e["type"] for e in events] == ["run.queued"]
    assert run["correlation_id"]


async def test_empty_command_rejected(client: httpx.AsyncClient) -> None:
    await onboard(client)
    response = await client.post("/api/v1/commands", json={"text": "   "})
    assert response.status_code == 400


async def test_kill_switch_blocks_commands(client: httpx.AsyncClient) -> None:
    await onboard(client)
    await client.patch("/api/v1/settings", json={"kill_switch": True})
    response = await client.post("/api/v1/commands", json={"text": "do something"})
    assert response.status_code == 423


async def test_skill_run_endpoint_and_history(
    client: httpx.AsyncClient, workspace_unused: None = None
) -> None:
    await onboard(client)
    run = (
        await client.post(
            "/api/v1/skills/decision-memo/run",
            json={
                "input": {
                    "decision": "Choose the deployment target",
                    "options": [{"name": "a"}, {"name": "b"}],
                },
            },
        )
    ).json()
    from cockpit.worker import process_run_inline

    await process_run_inline(run["id"])
    detail = (await client.get(f"/api/v1/runs/{run['id']}")).json()
    assert detail["status"] == "completed"
    artifacts = (await client.get(f"/api/v1/artifacts?run_id={run['id']}")).json()
    assert len(artifacts) == 2
    content = (await client.get(f"/api/v1/artifacts/{artifacts[0]['id']}")).json()
    assert content["content"]
    events = (await client.get(f"/api/v1/runs/{run['id']}/events")).json()
    assert events[-1]["type"] == "run.completed"
    assert all("human_text" in e for e in events)


async def test_skill_autonomy_patch_never_auto(client: httpx.AsyncClient) -> None:
    await onboard(client)
    skill = (await client.get("/api/v1/skills/project-pulse")).json()
    assert skill["autonomy"] == 3
    updated = (await client.patch("/api/v1/skills/project-pulse", json={"autonomy": 1})).json()
    assert updated["autonomy"] == 1


async def test_connector_listing_and_readonly_toggle(client: httpx.AsyncClient) -> None:
    await onboard(client)
    connectors = (await client.get("/api/v1/connectors")).json()
    slugs = {c["slug"] for c in connectors}
    assert {
        "local-files",
        "obsidian",
        "n8n",
        "mcp",
        "google-workspace",
        "notion",
        "github",
    } <= slugs
    mocks = [c for c in connectors if c["slug"] == "google-workspace"]
    assert mocks[0]["manifest"]["mock"] is True
    patched = (
        await client.patch("/api/v1/connectors/local-files", json={"mode": "read_only"})
    ).json()
    assert patched["mode"] == "read_only"


async def test_connector_config_rejects_secret_values(client: httpx.AsyncClient) -> None:
    await onboard(client)
    response = await client.patch(
        "/api/v1/connectors/n8n",
        json={
            "config": {
                "webhooks": [
                    {"name": "x", "url": "https://h", "token": "sk-ant-abc123def456ghi789jkl"}
                ]
            },
        },
    )
    assert response.status_code == 400
    assert "environment variables" in response.json()["detail"]


async def test_n8n_webhook_registration_creates_tool(client: httpx.AsyncClient) -> None:
    await onboard(client)
    response = await client.post(
        "/api/v1/connectors",
        json={
            "kind": "n8n_webhook",
            "name": "crm_sync",
            "url": "https://n8n.local/webhook/crm",
            "read_only": False,
            "supports_dry_run": True,
        },
    )
    assert response.status_code == 201
    tools = (await client.get("/api/v1/connectors/n8n/tools")).json()
    assert any(t["tool_id"] == "n8n.crm_sync" and t["risk_level"] == "R3" for t in tools)


async def test_mcp_inproc_registration(client: httpx.AsyncClient) -> None:
    await onboard(client)
    response = await client.post(
        "/api/v1/connectors",
        json={
            "kind": "mcp_server",
            "name": "demo-tools",
            "transport": "inproc",
        },
    )
    assert response.status_code == 201
    tools = (await client.get("/api/v1/connectors/mcp/tools")).json()
    ids = {t["tool_id"] for t in tools}
    assert {"mcp.demo-tools.echo", "mcp.demo-tools.todo_add"} <= ids


async def test_automation_shadow_mode_run(client: httpx.AsyncClient) -> None:
    await onboard(client)
    schedule = (
        await client.post(
            "/api/v1/automations",
            json={
                "skill_slug": "morning-brief",
                "shadow_mode": True,
                "interval_minutes": 1440,
            },
        )
    ).json()
    assert schedule["shadow_mode"] is True
    run = (await client.post(f"/api/v1/automations/{schedule['id']}/run-now")).json()
    assert run["shadow"] is True and run["mode"] == "draft"
    from cockpit.worker import process_run_inline

    await process_run_inline(run["id"])
    detail = (await client.get(f"/api/v1/runs/{run['id']}")).json()
    assert detail["status"] == "completed"


async def test_domain_high_sensitivity_stays_read_only(client: httpx.AsyncClient) -> None:
    await onboard(client)
    domains = {d["key"]: d for d in (await client.get("/api/v1/domains")).json()}
    assert domains["health"]["enabled"] is False
    assert domains["money"]["read_only"] is True
    response = await client.patch("/api/v1/domains/health", json={"read_only": False})
    assert response.status_code == 400


async def test_memory_review_approve_creates_commitment(client: httpx.AsyncClient) -> None:
    await onboard(client)
    from tests.conftest import submit_and_process

    ws_id = (await client.get("/api/v1/onboarding/status")).json()["workspace_id"]
    await submit_and_process(ws_id, skill_slug="commitment-sweep")
    proposed = (await client.get("/api/v1/memories?status=proposed")).json()
    assert proposed
    memory_id = proposed[0]["id"]
    approved = (
        await client.patch(f"/api/v1/memories/{memory_id}", json={"action": "approve"})
    ).json()
    assert approved["status"] == "active"
    agenda = (await client.get("/api/v1/agenda")).json()
    assert any(c["title"] == proposed[0]["content"] for c in agenda["commitments"])
    export = await client.get("/api/v1/memories/export")
    assert export.status_code == 200 and export.json()["memories"]


async def test_doctor_reports(client: httpx.AsyncClient) -> None:
    await onboard(client)
    report = (await client.get("/api/v1/doctor")).json()
    assert report["status"] in ("ok", "warn")
    names = {c["name"] for c in report["checks"]}
    assert "Database migrated" in names or any("Database" in n for n in names)
    for check in report["checks"]:
        if check["status"] == "fail":
            assert check["fix"], f"failed check {check['name']} must include a fix"


async def test_usage_endpoint(client: httpx.AsyncClient) -> None:
    await onboard(client)
    usage = (await client.get("/api/v1/usage")).json()
    assert set(usage) == {"today", "week", "budgets"}
