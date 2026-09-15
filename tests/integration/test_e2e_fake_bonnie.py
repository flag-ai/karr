"""The plan §10.3 end-to-end scenario against a scripted fake BONNIE.

1. Provision. 2. Fetch install.sh and check the token, server URL, quoting and
systemd unit. 3. Register. 4. The agent is online at the first poll. 5. Create
an environment, start it, stream its log (keepalives arrive between lines;
the timings are scaled down from the 60 s that Go's write timeout would have
cut off) and stop it. 6. Kill the container behind KARR's back and let the
reconciler mark it. 7. Deleting the agent is refused, then forced.
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import AsyncIterator

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from karr.api import sse
from karr.api.routers import environments as env_router
from karr.services.reconcile import reconcile_once

pytestmark = pytest.mark.integration

HOST = "192.168.1.50"
BONNIE = f"http://{HOST}:7777"


class _SlowLog(httpx.AsyncByteStream):
    """Two lines with a pause between them, so the relay has to keep the link alive."""

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b"data: booting\n\n"
        await asyncio.sleep(0.3)
        yield b"data: ready\n\n"


def _mock_bonnie() -> None:
    respx.get(f"{BONNIE}/health").mock(
        return_value=httpx.Response(200, json={"healthy": True})
    )
    respx.get(f"{BONNIE}/api/v1/system/info").mock(
        return_value=httpx.Response(
            200,
            json={
                "system": {
                    "hostname": "gpu-03",
                    "os": "linux",
                    "arch": "amd64",
                    "kernel": "6.19",
                    "cpu_model": "x",
                    "cpu_cores": 8,
                    "memory_mb": 65536,
                }
            },
        )
    )
    respx.get(f"{BONNIE}/api/v1/gpu/status").mock(
        return_value=httpx.Response(
            200, json={"vendor": "none", "gpus": None}
        )  # K-D17 shape
    )
    respx.get(f"{BONNIE}/api/v1/containers").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "ctr-e2e",
                    "name": "env-e2e",
                    "image": "img",
                    "state": "running",
                    "status": "Up",
                    "created": 1,
                }
            ],
        )
    )
    respx.post(f"{BONNIE}/api/v1/containers").mock(
        return_value=httpx.Response(201, json={"id": "ctr-e2e"})
    )
    respx.post(f"{BONNIE}/api/v1/containers/ctr-e2e/start").mock(
        return_value=httpx.Response(200, json={"status": "started"})
    )
    respx.post(f"{BONNIE}/api/v1/containers/ctr-e2e/stop").mock(
        return_value=httpx.Response(200, json={"status": "stopped"})
    )
    respx.get(f"{BONNIE}/api/v1/containers/ctr-e2e/logs").mock(
        return_value=httpx.Response(
            200, stream=_SlowLog(), headers={"Content-Type": "text/event-stream"}
        )
    )


@respx.mock
def test_end_to_end_with_fake_bonnie(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_bonnie()
    # keepalives every 50 ms instead of 15 s: the mechanism is what matters here
    monkeypatch.setattr(
        env_router, "relay", functools.partial(sse.relay, keepalive_seconds=0.05)
    )

    # 1. provision
    prov = api.post("/api/v1/agents/provision", json={"label": "gpu-03"})
    assert prov.status_code == 201, prov.text
    token = prov.json()["token"]
    assert prov.json()["install_command"] == (
        f"curl -fsSL 'https://karr.test/api/v1/install.sh?token={token}' | sudo bash -s --"
    )

    # 2. the install script, fetched without the admin token like the host does
    anon = TestClient(
        api.app, base_url="http://karr.test", client=("203.0.113.9", 4000)
    )
    script = anon.get(f"/api/v1/install.sh?token={token}")
    assert script.status_code == 200 and script.headers["content-type"].startswith(
        "text/x-shellscript"
    )
    body = script.text
    assert body.startswith("#!/usr/bin/env bash\nset -euo pipefail\n")
    assert (
        f"REGISTRATION_TOKEN={token}\n" in body
        and "SERVER_URL=https://karr.test\n" in body
    )
    assert (
        "[Unit]" in body
        and "[Service]" in body
        and "ExecStart=/usr/local/bin/bonnie" in body
    )
    assert '"${SERVER_URL}/api/v1/agents/register"' in body  # quoted expansion
    assert (
        "'" not in token and '"' not in token
    )  # nothing that could break the script's quoting

    # 3. register, as BONNIE's installer does
    reg = anon.post(
        "/api/v1/agents/register",
        json={
            "registration_token": token,
            "port": 7777,
            "auth_token": "agent-auth",
            "address": HOST,
        },
    )
    assert reg.status_code == 201, reg.text
    aid = reg.json()["agent_id"]
    assert api.get(f"/api/v1/install.sh?token={token}").status_code == 410  # spent

    # 4. online at the first poll
    registry = api.app.state.registry  # type: ignore[attr-defined]
    api.portal.call(registry.poll)
    agent = api.get(f"/api/v1/agents/{aid}").json()
    assert (
        agent["status"] == "online"
        and agent["url"] == BONNIE
        and agent["name"] == "gpu-03"
    )
    status = api.get(f"/api/v1/agents/{aid}/status").json()
    assert (
        status["system"]["system"]["hostname"] == "gpu-03"
        and status["gpu"]["gpus"] is None
    )

    # 5. environment lifecycle with a streamed log
    env = api.post(
        "/api/v1/environments",
        json={"agent_id": aid, "name": "env-e2e", "image": "img"},
    )
    assert env.status_code == 201, env.text
    eid = env.json()["id"]
    assert env.json()["status"] == "stopped" and env.json()["container_id"] == "ctr-e2e"
    assert api.post(f"/api/v1/environments/{eid}/start").status_code == 204
    assert api.get(f"/api/v1/environments/{eid}").json()["status"] == "running"
    with api.stream("GET", f"/api/v1/environments/{eid}/logs") as stream:
        assert stream.status_code == 200
        text = b"".join(stream.iter_bytes()).decode()
    frames = text.split("\n\n")
    assert frames[0] == "data: booting" and "data: ready" in frames
    assert frames.count(": keepalive") >= 2  # the pause was bridged, not cut
    assert (
        frames[-2] == "event: end\ndata: "
    )  # K-D2: an explicit end, not a silent close
    assert api.post(f"/api/v1/environments/{eid}/stop").status_code == 204
    assert api.get(f"/api/v1/environments/{eid}").json()["status"] == "stopped"

    # 6. the container disappears behind KARR's back
    respx.get(f"{BONNIE}/api/v1/containers").mock(
        return_value=httpx.Response(200, json=[])
    )
    sessions = api.app.state.session_factory  # type: ignore[attr-defined]
    assert api.portal.call(reconcile_once, sessions, registry) == 1
    row = api.get(f"/api/v1/environments/{eid}").json()
    assert row["status"] == "error" and row["status_message"] == "container missing"

    # 7. the agent cannot be deleted while it has environments, unless forced
    refused = api.delete(f"/api/v1/agents/{aid}")
    assert refused.status_code == 409 and "force=true" in refused.json()["error"]
    respx.delete(f"{BONNIE}/api/v1/containers/ctr-e2e").mock(
        return_value=httpx.Response(404)
    )
    assert api.delete(f"/api/v1/agents/{aid}?force=true").status_code == 204
    assert (
        api.get("/api/v1/agents").json() == []
        and api.get("/api/v1/environments").json() == []
    )
