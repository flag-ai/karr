"""Provisioning, install script and self-registration (routes 4–8)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from flag_commons.database import create_sync_engine
from sqlalchemy import text

from karr.app import create_app
from karr.config import KarrConfig

pytestmark = pytest.mark.integration
ZERO = "00000000-0000-0000-0000-000000000000"


@pytest.fixture(autouse=True)
def _reset_limiters(api: TestClient) -> None:
    api.app.state.provision_limiter.reset()  # type: ignore[attr-defined]
    api.app.state.register_limiter.reset()  # type: ignore[attr-defined]


def _db_url(api: TestClient) -> str:
    return api.app.state.config.database_url.get_secret_value()  # type: ignore[attr-defined]


@respx.mock
def test_provision_install_and_register(api: TestClient) -> None:
    respx.get("http://192.168.1.50:7777/health").mock(
        return_value=httpx.Response(200, json={"healthy": True})
    )
    assert api.get("/api/v1/agents/registrations").json() == []
    assert api.post("/api/v1/agents/provision", json={"label": ""}).status_code == 422
    assert api.post("/api/v1/agents/provision", json={}).status_code == 422

    created = api.post("/api/v1/agents/provision", json={"label": " gpu-03 "})
    assert created.status_code == 201, created.text
    prov = created.json()
    token = prov["token"]
    assert len(token) == 64 and int(token, 16) >= 0
    assert prov["install_command"].startswith(
        "curl -fsSL 'https://karr.test/api/v1/install.sh?token="
    )
    assert prov["install_command"].endswith(
        "| sudo bash -s --"
    )  # FIX: --address passes the pipe
    assert prov["expires_at"].endswith("Z")
    rid = prov["id"]

    pending = api.get("/api/v1/agents/registrations").json()
    assert [(r["label"], r["status"]) for r in pending] == [("gpu-03", "pending")]
    assert "agent_id" not in pending[0] and "claimed_at" not in pending[0]  # omitempty
    assert "token" not in pending[0] and "token_hash" not in pending[0]

    # K-D7: the script is served only for a known, pending, unexpired token.
    api.headers.pop("Authorization")
    assert api.get("/api/v1/install.sh").status_code == 400
    assert api.get("/api/v1/install.sh?token=bad$token").status_code == 400
    assert api.get("/api/v1/install.sh?token=deadbeef").status_code == 404
    script = api.get(f"/api/v1/install.sh?token={token}")
    assert script.status_code == 200, script.text
    assert script.headers["content-type"].startswith("text/x-shellscript")
    assert f"REGISTRATION_TOKEN={token}\n" in script.text
    assert (
        "SERVER_URL=https://karr.test\n" in script.text
    )  # allow_insecure? no: host is karr.test...
    assert script.headers["cache-control"] == "no-store"

    # self-registration (no admin token); XFF ignored because the peer is untrusted here
    body = {
        "registration_token": token,
        "port": 7777,
        "auth_token": "agent-auth-token",
        "address": "192.168.1.50",
    }
    assert (
        api.post(
            "/api/v1/agents/register", json={**body, "registration_token": "deadbeef"}
        ).status_code
        == 422
    )
    assert (
        api.post(
            "/api/v1/agents/register", json={"registration_token": token}
        ).status_code
        == 400
    )
    registered = api.post("/api/v1/agents/register", json=body)
    assert registered.status_code == 201, registered.text
    assert registered.json()["message"] == "agent registered successfully"
    agent_id = registered.json()["agent_id"]

    # replay of a claimed token fails (K-D6 transactional claim)
    assert api.post("/api/v1/agents/register", json=body).status_code == 422
    assert api.get(f"/api/v1/install.sh?token={token}").status_code == 410

    api.headers["Authorization"] = (
        f"Bearer {api.app.state.config.admin_token.get_secret_value()}"  # type: ignore[attr-defined]
    )
    claimed = api.get("/api/v1/agents/registrations").json()[0]
    assert claimed["status"] == "claimed" and claimed["agent_id"] == agent_id
    assert claimed["claimed_at"].endswith("Z")
    agents = api.get("/api/v1/agents").json()
    assert (
        agents[0]["name"] == "gpu-03" and agents[0]["url"] == "http://192.168.1.50:7777"
    )
    assert api.app.state.registry.get(agent_id) is not None  # type: ignore[attr-defined]
    with create_sync_engine(_db_url(api)).connect() as conn:
        stored = conn.execute(text("SELECT token_encrypted FROM karr_agents")).scalar()
    assert stored and "agent-auth-token" not in stored

    assert api.delete(f"/api/v1/agents/registrations/{rid}").status_code == 204
    assert api.delete(f"/api/v1/agents/registrations/{rid}").status_code == 404  # K-D5
    assert api.delete("/api/v1/agents/registrations/nope").json() == {
        "error": "invalid registration id"
    }


def test_register_uses_source_ip_and_label_fallback(api: TestClient) -> None:
    token = api.post("/api/v1/agents/provision", json={"label": "host-a"}).json()[
        "token"
    ]
    api.headers.pop("Authorization")
    # peer 10.0.0.1 is a trusted proxy in the integration config: XFF is honoured
    resp = api.post(
        "/api/v1/agents/register",
        json={"registration_token": token, "port": 8000, "auth_token": "t"},
        headers={"X-Forwarded-For": "203.0.113.9"},
    )
    assert resp.status_code == 201, resp.text
    api.headers["Authorization"] = (
        f"Bearer {api.app.state.config.admin_token.get_secret_value()}"  # type: ignore[attr-defined]
    )
    agents = api.get("/api/v1/agents").json()
    assert (
        agents[0]["url"] == "http://203.0.113.9:8000" and agents[0]["name"] == "host-a"
    )
    # duplicate label leaves the second registration claimable
    token2 = api.post("/api/v1/agents/provision", json={"label": "host-a"}).json()[
        "token"
    ]
    api.headers.pop("Authorization")
    dup = api.post(
        "/api/v1/agents/register",
        json={"registration_token": token2, "port": 8000, "auth_token": "t"},
    )
    assert dup.status_code == 422
    assert (
        api.get(f"/api/v1/install.sh?token={token2}").status_code == 200
    )  # still pending


def test_expiry_is_computed_on_read(api: TestClient) -> None:
    rid = api.post("/api/v1/agents/provision", json={"label": "old"}).json()["id"]
    engine = create_sync_engine(_db_url(api))
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE karr_agent_registrations SET expires_at = :t WHERE id = :id"),
            {"t": datetime.now(timezone.utc) - timedelta(seconds=1), "id": rid},
        )
    engine.dispose()
    listed = api.get("/api/v1/agents/registrations").json()
    assert listed[0]["status"] == "expired"  # K-D8
    token = api.post("/api/v1/agents/provision", json={"label": "fresh"}).json()[
        "token"
    ]
    api.headers.pop("Authorization")
    engine = create_sync_engine(_db_url(api))
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE karr_agent_registrations SET expires_at = now() - interval '1 second'"
            )
        )
    engine.dispose()
    assert api.get(f"/api/v1/install.sh?token={token}").status_code == 410
    assert (
        api.post(
            "/api/v1/agents/register",
            json={"registration_token": token, "port": 1, "auth_token": "t"},
        ).status_code
        == 422
    )


def test_rate_limits_are_per_client(api: TestClient) -> None:
    api.app.state.provision_limiter.reset()  # type: ignore[attr-defined]
    api.app.state.provision_limiter.capacity = 2  # type: ignore[attr-defined]
    assert api.post("/api/v1/agents/provision", json={"label": "a"}).status_code == 201
    assert api.post("/api/v1/agents/provision", json={"label": "b"}).status_code == 201
    limited = api.post("/api/v1/agents/provision", json={"label": "c"})
    assert limited.status_code == 429 and limited.json() == {
        "error": "rate limited; retry shortly"
    }  # K-D23
    assert int(limited.headers["retry-after"]) >= 1
    api.app.state.provision_limiter.capacity = 30  # type: ignore[attr-defined]

    # install.sh and register share the register limiter, keyed by client:
    # one abusive host does not block another.
    api.headers.pop("Authorization")
    api.app.state.register_limiter.capacity = 1  # type: ignore[attr-defined]
    api.app.state.register_limiter.reset()  # type: ignore[attr-defined]
    assert api.get("/api/v1/install.sh?token=deadbeef").status_code == 404
    assert api.get("/api/v1/install.sh?token=deadbeef").status_code == 429
    other = TestClient(api.app, base_url="http://karr.test", client=("10.0.0.2", 50001))
    assert other.get("/api/v1/install.sh?token=deadbeef").status_code == 404
    api.app.state.register_limiter.capacity = 30  # type: ignore[attr-defined]


def test_register_rejects_hostile_address(api: TestClient) -> None:
    token = api.post("/api/v1/agents/provision", json={"label": "h"}).json()["token"]
    api.headers.pop("Authorization")
    for address in (
        "user:pw@internal",
        "evil.com#",
        "a b",
        "attacker.example/path",
        "1.2.3.4 --bad",
        "1.2.3.4:443",  # would smuggle a port: http://1.2.3.4:443:7777
    ):
        resp = api.post(
            "/api/v1/agents/register",
            json={
                "registration_token": token,
                "port": 7777,
                "auth_token": "t",
                "address": address,
            },
        )
        assert resp.status_code == 422, address
    # the token is still claimable after the rejected attempts, and IPv6 literals work
    assert api.get(f"/api/v1/install.sh?token={token}").status_code == 200
    ok = api.post(
        "/api/v1/agents/register",
        json={
            "registration_token": token,
            "port": 7777,
            "auth_token": "t",
            "address": "[fd00::10]",
        },
    )
    assert ok.status_code == 201, ok.text


def test_server_url_never_comes_from_headers(
    live_config: KarrConfig, clean_tables: None
) -> None:
    cfg = live_config.model_copy(update={"public_url": ""})
    auth = f"Bearer {live_config.admin_token.get_secret_value()}"
    fwd = {
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Host": "evil.example",
        "Host": "evil.example",
    }
    # even from a trusted proxy: refused rather than embedded in `curl | sudo bash`
    with TestClient(
        create_app(cfg), base_url="http://karr.test", client=("10.0.0.1", 4000)
    ) as c:
        c.headers["Authorization"] = auth
        resp = c.post("/api/v1/agents/provision", json={"label": "x"}, headers=fwd)
        assert resp.status_code == 503 and "KARR_PUBLIC_URL" in resp.json()["error"]
        assert (
            c.get("/api/v1/agents/registrations").json() == []
        )  # nothing was left behind
        c.headers.pop("Authorization")
        assert (
            c.get("/api/v1/install.sh?token=" + "a" * 64, headers=fwd).status_code
            == 404
        )


def test_registration_routes_require_admin(api: TestClient) -> None:
    api.headers.pop("Authorization")
    assert api.post("/api/v1/agents/provision", json={"label": "x"}).status_code == 401
    assert api.get("/api/v1/agents/registrations").status_code == 401
    assert api.delete(f"/api/v1/agents/registrations/{ZERO}").status_code == 401
