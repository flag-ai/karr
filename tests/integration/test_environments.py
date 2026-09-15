"""Environments (routes 19–25) against the live database, BONNIE mocked with respx."""

from __future__ import annotations

import asyncio
import contextlib
import functools
from collections.abc import AsyncIterator

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from flag_commons.database import create_sync_engine
from sqlalchemy import text

from karr.services.reconcile import reconcile_once

pytestmark = pytest.mark.integration
ZERO = "00000000-0000-0000-0000-000000000000"
BONNIE = "http://gpu-01.test:7777"
BONNIE2 = "http://gpu-02.test:7777"


class _ByteStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes], *, endless: bool = False) -> None:
        self._chunks = chunks
        self._endless = endless
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk
        while self._endless:
            yield b"data: tick\n\n"
            await asyncio.sleep(0.01)

    async def aclose(self) -> None:
        self.closed = True


def _mock_bonnie(container_state: str = "running") -> None:
    respx.get(f"{BONNIE}/health").mock(
        return_value=httpx.Response(200, json={"healthy": True})
    )
    respx.post(f"{BONNIE}/api/v1/containers").mock(
        return_value=httpx.Response(201, json={"id": "ctr-1"})
    )
    respx.post(f"{BONNIE}/api/v1/containers/ctr-1/start").mock(
        return_value=httpx.Response(200, json={"status": "started"})
    )
    respx.post(f"{BONNIE}/api/v1/containers/ctr-1/stop").mock(
        return_value=httpx.Response(200, json={"status": "stopped"})
    )
    respx.delete(f"{BONNIE}/api/v1/containers/ctr-1").mock(
        return_value=httpx.Response(204)
    )
    respx.get(f"{BONNIE}/api/v1/containers").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "ctr-1",
                    "name": "env-1",
                    "image": "img",
                    "state": container_state,
                    "status": "Up",
                    "created": 1,
                }
            ],
        )
    )
    respx.get(f"{BONNIE}/api/v1/containers/ctr-1/logs").mock(
        return_value=httpx.Response(
            200,
            stream=_ByteStream(
                [
                    b"data: container starting...\n\n",
                    b"data: loading model weights\nline two\n\n",
                    b"data: with\rreturn\n\n",
                ]
            ),
            headers={"Content-Type": "text/event-stream"},
        )
    )


def _url(api: TestClient) -> str:
    return api.app.state.config.database_url.get_secret_value()  # type: ignore[attr-defined]


def _set_creating(api: TestClient, eid: str, *, age_seconds: int) -> None:
    """Simulate a crash mid-create: the row is `creating` with no container."""
    engine = create_sync_engine(_url(api))
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE karr_environments SET status = 'creating', container_id = '',"
                " created_at = now() - make_interval(secs => :age) WHERE id = :id"
            ),
            {"id": eid, "age": age_seconds},
        )
    engine.dispose()


def _agent(api: TestClient, name: str = "gpu-01", url: str = BONNIE) -> str:
    created = api.post("/api/v1/agents", json={"name": name, "url": url, "token": "t"})
    assert created.status_code == 201, created.text
    return created.json()["id"]


@respx.mock
def test_environment_lifecycle(api: TestClient) -> None:
    _mock_bonnie()
    aid = _agent(api)
    project = api.post("/api/v1/projects", json={"name": "p"}).json()
    assert api.get("/api/v1/environments").json() == []

    bad_agent = api.post(
        "/api/v1/environments", json={"agent_id": ZERO, "name": "x", "image": "img"}
    )
    assert bad_agent.status_code == 400 and bad_agent.json() == {
        "error": "agent not found"
    }  # K-D5
    bad_project = api.post(
        "/api/v1/environments",
        json={"agent_id": aid, "project_id": ZERO, "name": "x", "image": "img"},
    )
    assert bad_project.status_code == 400 and bad_project.json() == {
        "error": "project not found"
    }  # K-D5
    blank = api.post(
        "/api/v1/environments", json={"agent_id": aid, "name": "  ", "image": "img"}
    )
    assert blank.status_code == 422 and blank.json() == {"error": "name is required"}
    assert (
        api.post(
            "/api/v1/environments", json={"agent_id": aid, "name": "x"}
        ).status_code
        == 422
    )
    assert (
        api.post(
            "/api/v1/environments", json={"agent_id": aid, "image": "img"}
        ).status_code
        == 422
    )
    assert (
        api.post(
            "/api/v1/environments",
            json={"agent_id": "nope", "name": "x", "image": "img"},
        ).status_code
        == 422
    )

    body = {
        "agent_id": aid,
        "project_id": project["id"],
        "name": " env-1 ",
        "image": "vllm/vllm-openai:latest",
        "gpu": True,
        "env": ["A=1"],
        "mounts": ["/models:/models"],
        "command": ["python", "-m", "vllm"],
    }
    created = api.post("/api/v1/environments", json=body)
    assert created.status_code == 201, created.text
    env = created.json()
    assert (
        env["status"] == "stopped"
        and env["container_id"] == "ctr-1"
        and env["name"] == "env-1"
    )
    assert (
        env["project_id"] == project["id"]
        and env["env"] == ["A=1"]
        and env["gpu"] is True
    )
    assert "status_message" not in env
    eid = env["id"]
    sent = respx.calls.last.request  # the create-container call
    assert sent.method == "POST"

    assert (
        api.post(
            "/api/v1/environments",
            json={"agent_id": aid, "name": "env-1", "image": "img"},
        ).status_code
        == 409
    )  # K-D22
    assert api.get("/api/v1/environments").json()[0]["id"] == eid
    assert api.get(f"/api/v1/environments/{eid}").json()["id"] == eid
    assert api.get(f"/api/v1/environments/{ZERO}").json() == {
        "error": "environment not found"
    }
    assert api.get("/api/v1/environments/not-a-uuid").json() == {
        "error": "invalid environment id"
    }

    # K-D3 transition guards
    assert api.post(f"/api/v1/environments/{eid}/stop").status_code == 409
    assert api.post(f"/api/v1/environments/{eid}/start").status_code == 204
    assert api.get(f"/api/v1/environments/{eid}").json()["status"] == "running"
    assert api.post(f"/api/v1/environments/{eid}/start").status_code == 409
    assert api.post(f"/api/v1/environments/{ZERO}/start").status_code == 404

    # K-D2: the relay escapes line terminators, ends with event: end
    with api.stream("GET", f"/api/v1/environments/{eid}/logs") as stream:
        assert stream.status_code == 200
        assert stream.headers["content-type"].startswith("text/event-stream")
        assert stream.headers["cache-control"] == "no-cache"
        text_body = b"".join(stream.iter_bytes()).decode()
    assert text_body == (
        "data: container starting...\n\n"
        "data: loading model weights\n\n"
        "data: line two\n\n"
        "data: with\\rreturn\n\n"
        "event: end\ndata: \n\n"
    )
    assert (
        api.get(f"/api/v1/environments/{ZERO}/logs").status_code == 404
    )  # before any headers

    assert api.post(f"/api/v1/environments/{eid}/stop").status_code == 204
    assert api.get(f"/api/v1/environments/{eid}").json()["status"] == "stopped"

    # the agent cannot be deleted while the environment exists (K-D4)
    assert api.delete(f"/api/v1/agents/{aid}").status_code == 409
    assert api.delete(f"/api/v1/environments/{eid}").status_code == 204
    assert api.delete(f"/api/v1/environments/{eid}").status_code == 404
    assert api.get("/api/v1/environments").json() == []
    assert api.delete(f"/api/v1/agents/{aid}").status_code == 204


@respx.mock
def test_bonnie_failures_leave_error_status(api: TestClient) -> None:
    _mock_bonnie()
    aid = _agent(api)
    respx.post(f"{BONNIE}/api/v1/containers").mock(
        return_value=httpx.Response(500, json={"error": "no such image"})
    )
    failed = api.post(
        "/api/v1/environments",
        json={"agent_id": aid, "name": "env-x", "image": "missing:latest"},
    )
    assert failed.status_code == 502 and "no such image" in failed.json()["error"]
    rows = api.get("/api/v1/environments").json()
    assert rows[0]["status"] == "error" and "no such image" in rows[0]["status_message"]
    assert "container_id" not in rows[0]
    eid = rows[0]["id"]
    assert (
        api.post(f"/api/v1/environments/{eid}/start").status_code == 409
    )  # error is not startable
    assert (
        api.get(f"/api/v1/environments/{eid}/logs").status_code == 409
    )  # no container, before headers
    assert (
        api.delete(f"/api/v1/environments/{eid}").status_code == 204
    )  # no container: row only

    respx.post(f"{BONNIE}/api/v1/containers").mock(
        return_value=httpx.Response(201, json={"id": "ctr-1"})
    )
    eid = api.post(
        "/api/v1/environments", json={"agent_id": aid, "name": "env-y", "image": "img"}
    ).json()["id"]
    respx.post(f"{BONNIE}/api/v1/containers/ctr-1/start").mock(
        side_effect=httpx.ConnectError("down")
    )
    assert api.post(f"/api/v1/environments/{eid}/start").status_code == 502
    assert api.get(f"/api/v1/environments/{eid}").json()["status"] == "error"
    # a container already gone counts as removed
    respx.delete(f"{BONNIE}/api/v1/containers/ctr-1").mock(
        return_value=httpx.Response(404, json={"error": "gone"})
    )
    assert api.delete(f"/api/v1/environments/{eid}").status_code == 204


@respx.mock
def test_reconciliation(api: TestClient) -> None:
    _mock_bonnie(container_state="running")
    aid = _agent(api)
    eid = api.post(
        "/api/v1/environments", json={"agent_id": aid, "name": "env-1", "image": "img"}
    ).json()["id"]
    assert api.post(f"/api/v1/environments/{eid}/start").status_code == 204
    registry = api.app.state.registry  # type: ignore[attr-defined]
    api.portal.call(registry.poll)  # marks the agent online
    sessions = api.app.state.session_factory  # type: ignore[attr-defined]

    assert (
        api.portal.call(reconcile_once, sessions, registry) == 0
    )  # running == running
    respx.get(f"{BONNIE}/api/v1/containers").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "ctr-1",
                    "name": "env-1",
                    "image": "img",
                    "state": "exited",
                    "status": "Exited (0)",
                    "created": 1,
                }
            ],
        )
    )
    assert api.portal.call(reconcile_once, sessions, registry) == 1
    assert api.get(f"/api/v1/environments/{eid}").json()["status"] == "stopped"
    respx.get(f"{BONNIE}/api/v1/containers").mock(
        return_value=httpx.Response(200, json=[])
    )
    assert api.portal.call(reconcile_once, sessions, registry) == 1
    row = api.get(f"/api/v1/environments/{eid}").json()
    assert (
        row["status"] == "error" and row["status_message"] == "container missing"
    )  # K-D3
    # a row stuck in `creating` (crash between create and commit) is adopted by
    # name, but only once it is older than the create grace period
    _set_creating(api, eid, age_seconds=0)
    respx.get(f"{BONNIE}/api/v1/containers").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "ctr-9",
                    "name": "env-1",
                    "image": "img",
                    "state": "running",
                    "status": "Up",
                    "created": 1,
                }
            ],
        )
    )
    assert api.portal.call(reconcile_once, sessions, registry) == 0  # in flight
    assert api.delete(f"/api/v1/environments/{eid}").status_code == 409  # in flight
    _set_creating(api, eid, age_seconds=600)
    assert api.portal.call(reconcile_once, sessions, registry) == 1
    row = api.get(f"/api/v1/environments/{eid}").json()
    assert row["status"] == "running" and row["container_id"] == "ctr-9"
    # ... and becomes an error when nothing on the agent carries its name
    _set_creating(api, eid, age_seconds=600)
    respx.get(f"{BONNIE}/api/v1/containers").mock(
        return_value=httpx.Response(200, json=[])
    )
    assert api.portal.call(reconcile_once, sessions, registry) == 1
    row = api.get(f"/api/v1/environments/{eid}").json()
    assert row["status"] == "error" and "never completed" in row["status_message"]
    assert api.delete(f"/api/v1/environments/{eid}").status_code == 204


@respx.mock
def test_reconcile_isolates_agents(api: TestClient) -> None:
    """One agent failing (or hanging) must not stop the pass for the others."""
    _mock_bonnie(container_state="exited")
    aid = _agent(api)
    eid = api.post(
        "/api/v1/environments", json={"agent_id": aid, "name": "env-1", "image": "img"}
    ).json()["id"]
    assert api.post(f"/api/v1/environments/{eid}/start").status_code == 204
    respx.get(f"{BONNIE2}/health").mock(
        return_value=httpx.Response(200, json={"healthy": True})
    )
    respx.get(f"{BONNIE2}/api/v1/containers").mock(
        return_value=httpx.Response(500, json={"error": "docker down"})
    )
    _agent(api, name="gpu-02", url=BONNIE2)
    registry = api.app.state.registry  # type: ignore[attr-defined]
    api.portal.call(registry.poll)
    assert {a.status for a in registry.agents()} == {"online"}
    sessions = api.app.state.session_factory  # type: ignore[attr-defined]

    assert api.portal.call(reconcile_once, sessions, registry) == 1
    assert api.get(f"/api/v1/environments/{eid}").json()["status"] == "stopped"

    async def hang(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200, json=[])

    respx.get(f"{BONNIE2}/api/v1/containers").mock(side_effect=hang)
    respx.get(f"{BONNIE}/api/v1/containers").mock(
        return_value=httpx.Response(200, json=[])
    )
    assert (
        api.portal.call(
            functools.partial(reconcile_once, per_agent_timeout=0.05),
            sessions,
            registry,
        )
        == 1
    )
    assert api.get(f"/api/v1/environments/{eid}").json()["status"] == "error"
    # BONNIE answers 500 (not 404) for a container it no longer has; the row is
    # still deletable because the reconciler already marked it missing
    respx.delete(f"{BONNIE}/api/v1/containers/ctr-1").mock(
        return_value=httpx.Response(500, json={"error": "failed to remove container"})
    )
    assert api.delete(f"/api/v1/environments/{eid}").status_code == 204


def test_environment_routes_require_admin(api: TestClient) -> None:
    api.headers.pop("Authorization")
    assert api.get("/api/v1/environments").status_code == 401
    assert (
        api.post(
            "/api/v1/environments", json={"agent_id": ZERO, "name": "x", "image": "i"}
        ).status_code
        == 401
    )
    for path in ("", "/start", "/stop", "/logs"):
        method = "get" if path in ("", "/logs") else "post"
        assert (
            getattr(api, method)(f"/api/v1/environments/{ZERO}{path}").status_code
            == 401
        )
    assert api.delete(f"/api/v1/environments/{ZERO}").status_code == 401


@respx.mock
def test_log_stream_slot_cap(api: TestClient) -> None:
    _mock_bonnie()
    aid = _agent(api)
    eid = api.post(
        "/api/v1/environments", json={"agent_id": aid, "name": "env-1", "image": "img"}
    ).json()["id"]
    slots = api.app.state.log_slots  # type: ignore[attr-defined]
    slots.per_key = 1
    release = slots.acquire(aid)  # another viewer already holds the agent's only slot
    try:
        resp = api.get(f"/api/v1/environments/{eid}/logs")
        assert resp.status_code == 429
        assert "too many open log streams" in resp.json()["error"]
    finally:
        release()
    assert api.get(f"/api/v1/environments/{eid}/logs").status_code == 200
    assert slots.open(aid) == 0  # a finished stream gives its slot back


@pytest.mark.parametrize("spec_version", ["2.4", "2.3"])
@respx.mock
def test_log_stream_disconnect_releases_upstream(
    api: TestClient, spec_version: str
) -> None:
    """A client that goes away mid-stream frees the upstream connection and the slot.

    Driven at the ASGI level because the TestClient buffers streaming bodies.
    Spec 2.4 is uvicorn: the disconnect is an OSError from ``send``; 2.3 is the
    older shape where ``receive`` yields ``http.disconnect``.
    """
    _mock_bonnie()
    aid = _agent(api)
    eid = api.post(
        "/api/v1/environments", json={"agent_id": aid, "name": "env-1", "image": "img"}
    ).json()["id"]
    upstream = _ByteStream([b"data: hello\n\n"], endless=True)
    respx.get(f"{BONNIE}/api/v1/containers/ctr-1/logs").mock(
        return_value=httpx.Response(
            200, stream=upstream, headers={"Content-Type": "text/event-stream"}
        )
    )
    slots = api.app.state.log_slots  # type: ignore[attr-defined]

    async def drive() -> None:
        gone = asyncio.Event()
        seen = 0

        async def receive() -> dict[str, object]:
            await gone.wait()
            return {"type": "http.disconnect"}

        async def send(message: dict[str, object]) -> None:
            nonlocal seen
            if message["type"] == "http.response.body":
                seen += 1
                if seen > 1:  # the first chunk was delivered; now the client is gone
                    gone.set()
                    if spec_version == "2.4":
                        raise OSError("connection reset")
                    await asyncio.sleep(0)  # let the disconnect listener cancel us

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": spec_version},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": f"/api/v1/environments/{eid}/logs",
            "raw_path": f"/api/v1/environments/{eid}/logs".encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"host", b"karr.test"),
                (b"authorization", api.headers["Authorization"].encode()),
            ],
            "client": ("10.0.0.1", 50001),
            "server": ("karr.test", 80),
        }
        # ClientDisconnect (2.3) or the OSError itself (2.4) is the expected exit
        with contextlib.suppress(Exception):
            await api.app(scope, receive, send)  # type: ignore[arg-type]
        assert seen >= 2

    api.portal.call(drive)
    assert upstream.closed
    assert slots.open(aid) == 0
