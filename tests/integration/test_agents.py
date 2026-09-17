"""Agents (routes 9–13) against the live database, BONNIE mocked with respx."""

from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from flag_commons.database import create_sync_engine
from pydantic import SecretStr
from sqlalchemy import text

from karr.app import create_app
from karr.config import KarrConfig

pytestmark = pytest.mark.integration
ZERO = "00000000-0000-0000-0000-000000000000"
BONNIE = "http://gpu-01.test:7777"


def _mock_bonnie() -> None:
    respx.get(f"{BONNIE}/health").mock(
        return_value=httpx.Response(200, json={"healthy": True})
    )
    respx.get(f"{BONNIE}/api/v1/system/info").mock(
        return_value=httpx.Response(
            200,
            json={
                "system": {
                    "hostname": "gpu-01",
                    "os": "linux",
                    "arch": "amd64",
                    "cpu_cores": 32,
                    "memory_mb": 131072,
                },
                "disk": {
                    "total_gb": 2000,
                    "used_gb": 500,
                    "available_gb": 1500,
                    "used_percent": "25%",
                },
            },
        )
    )
    respx.get(f"{BONNIE}/api/v1/gpu/status").mock(
        return_value=httpx.Response(
            200,
            json={
                "vendor": "nvidia",
                "gpus": None,
                "timestamp": "2026-09-14T00:00:00Z",
            },
        )
    )


def _db_url(api: TestClient) -> str:
    return api.app.state.config.database_url.get_secret_value()  # type: ignore[attr-defined]


@respx.mock
def test_agents_crud_and_status(api: TestClient) -> None:
    _mock_bonnie()
    assert api.get("/api/v1/agents").json() == []
    created = api.post(
        "/api/v1/agents",
        json={"name": " gpu-01 ", "url": BONNIE + "/", "token": "agent-secret"},
    )
    assert created.status_code == 201, created.text
    agent = created.json()
    assert (
        agent["name"] == "gpu-01"
        and agent["url"] == BONNIE
        and agent["status"] == "offline"
    )
    assert (
        "token" not in agent
        and "token_encrypted" not in agent
        and "agent-secret" not in created.text
    )
    assert "last_seen_at" not in agent  # Go omitempty: null keys are omitted
    aid = agent["id"]

    with create_sync_engine(_db_url(api)).connect() as conn:
        stored = conn.execute(text("SELECT token_encrypted FROM karr_agents")).scalar()
    assert stored and "agent-secret" not in stored  # encrypted at rest (K-D12)

    assert (
        api.post("/api/v1/agents", json={"name": "gpu-01", "url": BONNIE}).status_code
        == 409
    )  # K-D5
    assert (
        api.post("/api/v1/agents", json={"name": "x", "url": "ftp://x"}).status_code
        == 422
    )  # K-D13
    assert (
        api.post(
            "/api/v1/agents", json={"name": "x", "url": "http://u:p@h:1"}
        ).status_code
        == 422
    )
    assert (
        api.post("/api/v1/agents", json={"name": "", "url": BONNIE}).status_code == 422
    )
    assert api.post("/api/v1/agents", json={"url": BONNIE}).status_code == 422
    malformed = api.post(
        "/api/v1/agents",
        content=b"{not json",
        headers={"Content-Type": "application/json"},
    )
    assert malformed.status_code == 400

    assert api.get(f"/api/v1/agents/{aid}").json()["id"] == aid
    assert api.get(f"/api/v1/agents/{ZERO}").json() == {"error": "agent not found"}
    assert api.get("/api/v1/agents/not-a-uuid").json() == {"error": "invalid agent id"}

    # the registry got the agent immediately (Go upserted too); a poll marks it online
    registry = api.app.state.registry  # type: ignore[attr-defined]
    assert registry.get(aid) is not None
    api.portal.call(registry.poll)
    listed = api.get("/api/v1/agents").json()
    assert listed[0]["status"] == "online" and listed[0]["last_seen_at"].endswith("Z")
    assert listed[0]["last_checked_at"].endswith("Z")  # K-D10

    status = api.get(f"/api/v1/agents/{aid}/status")
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["agent"]["id"] == aid
    assert body["system"]["system"]["hostname"] == "gpu-01"
    assert body["gpu"]["gpus"] is None  # K-D17 upstream: null stays null
    assert api.get(f"/api/v1/agents/{ZERO}/status").status_code == 404

    # BONNIE errors are omitted, the call still succeeds
    respx.get(f"{BONNIE}/api/v1/system/info").mock(return_value=httpx.Response(500))
    respx.get(f"{BONNIE}/api/v1/gpu/status").mock(
        side_effect=httpx.ConnectError("down")
    )
    degraded = api.get(f"/api/v1/agents/{aid}/status").json()
    assert (
        "system" not in degraded
        and "gpu" not in degraded
        and degraded["agent"]["id"] == aid
    )

    assert api.delete(f"/api/v1/agents/{aid}").status_code == 204
    assert api.delete(f"/api/v1/agents/{aid}").status_code == 404  # K-D5 (Go: 204)
    assert registry.get(aid) is None


@respx.mock
def test_agent_delete_with_environments(api: TestClient) -> None:
    _mock_bonnie()
    aid = api.post("/api/v1/agents", json={"name": "gpu-02", "url": BONNIE}).json()[
        "id"
    ]
    engine = create_sync_engine(_db_url(api))
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO karr_environments (agent_id, name, image, container_id, status) "
                "VALUES (:a, 'env-1', 'img', 'ctr-1', 'stopped'), (:a, 'env-2', 'img', 'ctr-2', 'stopped')"
            ),
            {"a": aid},
        )
    blocked = api.delete(f"/api/v1/agents/{aid}")
    assert (
        blocked.status_code == 409 and "environment" in blocked.json()["error"]
    )  # K-D4

    # A container that cannot be removed keeps the rows and names it (no false 204).
    respx.delete(f"{BONNIE}/api/v1/containers/ctr-1").mock(
        return_value=httpx.Response(204)
    )
    respx.delete(f"{BONNIE}/api/v1/containers/ctr-2").mock(
        return_value=httpx.Response(500)
    )
    partial = api.delete(f"/api/v1/agents/{aid}?force=true")
    assert partial.status_code == 409 and "env-2" in partial.json()["error"]
    with engine.connect() as conn:
        assert (
            conn.execute(text("SELECT count(*) FROM karr_environments")).scalar() == 2
        )

    respx.delete(f"{BONNIE}/api/v1/containers/ctr-2").mock(
        return_value=httpx.Response(404)
    )
    forced = api.delete(f"/api/v1/agents/{aid}?force=true")
    assert forced.status_code == 204, forced.text
    with engine.connect() as conn:
        assert (
            conn.execute(text("SELECT count(*) FROM karr_environments")).scalar() == 0
        )
    engine.dispose()


def test_agents_require_admin(api: TestClient) -> None:
    api.headers.pop("Authorization")
    assert api.get("/api/v1/agents").status_code == 401
    assert (
        api.post("/api/v1/agents", json={"name": "x", "url": BONNIE}).status_code == 401
    )
    assert api.get(f"/api/v1/agents/{ZERO}").status_code == 401
    assert api.delete(f"/api/v1/agents/{ZERO}").status_code == 401
    assert api.get(f"/api/v1/agents/{ZERO}/status").status_code == 401


def test_default_agent_seeding(live_config: KarrConfig, clean_tables: None) -> None:
    cfg = live_config.model_copy(
        update={
            "default_agent_url": "http://default.test:7777/",
            "default_agent_token": SecretStr("tok"),
        }
    )
    auth = f"Bearer {live_config.admin_token.get_secret_value()}"
    for _ in range(2):  # idempotent across restarts
        with TestClient(create_app(cfg)) as client:
            client.headers["Authorization"] = auth
            agents = client.get("/api/v1/agents").json()
            assert [a["name"] for a in agents] == ["default"]
            assert agents[0]["url"] == "http://default.test:7777"
    bad = live_config.model_copy(
        update={"default_agent_url": "ftp://admin:pw@nope:21/"}
    )
    with TestClient(create_app(bad)) as client:
        client.headers["Authorization"] = auth
        assert [a["name"] for a in client.get("/api/v1/agents").json()] == [
            "default"
        ]  # rejected, not added
