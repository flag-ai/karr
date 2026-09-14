from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from karr import __version__
from karr.api.errors import ApiError
from karr.app import create_app, mount_spa
from karr.config import KarrConfig


def test_health_and_ready(client: TestClient) -> None:
    health = client.get("/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "ok" and body["version"].startswith(
        f"{__version__} (commit: "
    )
    ready = client.get("/ready")
    assert ready.status_code == 200 and ready.json()["healthy"] is True


def test_metrics(client: TestClient, auth: dict[str, str]) -> None:
    client.get("/api/v1/auth/check", headers=auth)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "karr_http_requests_total" in resp.text
    assert 'route="/api/v1/auth/check"' in resp.text
    assert "process_" in resp.text or "python_info" in resp.text


def test_security_headers(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    csp = resp.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp and "base-uri 'none'" in csp
    assert "strict-transport-security" not in resp.headers
    # Also present on responses produced by outer middleware (413, preflight).
    big = client.post("/api/v1/auth/check", headers={"Content-Length": "2000000"})
    assert big.status_code == 413 and big.headers["x-frame-options"] == "DENY"
    pre = client.options(
        "/api/v1/auth/check",
        headers={
            "Origin": "https://karr.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert pre.headers["x-frame-options"] == "DENY"


def test_hsts_opt_in(config: KarrConfig) -> None:
    cfg = config.model_copy(update={"enable_hsts": True})
    with TestClient(create_app(cfg, bootstrap=False)) as c:
        assert (
            "max-age=31536000" in c.get("/health").headers["strict-transport-security"]
        )


def test_cors(client: TestClient) -> None:
    resp = client.options(
        "/api/v1/auth/check",
        headers={
            "Origin": "https://karr.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "https://karr.example.com"
    assert resp.headers["access-control-max-age"] == "600"
    other = client.options(
        "/api/v1/auth/check",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in other.headers


def test_body_limit(config: KarrConfig, auth: dict[str, str]) -> None:
    app = create_app(config, bootstrap=False, spa=False)

    @app.post("/api/v1/echo")
    async def echo(payload: dict) -> dict:  # type: ignore[type-arg]
        return {"n": len(payload)}

    with TestClient(app) as client:
        declared = client.post(
            "/api/v1/echo", headers={**auth, "Content-Length": "2000000"}
        )
        assert declared.status_code == 413
        assert declared.json() == {"error": "request body too large"}
        # A streamed body with no Content-Length is cut off once it exceeds the cap.
        chunks = (b'{"k": "' + b"x" * 65536 + b'"}' for _ in range(32))
        streamed = client.post("/api/v1/echo", content=chunks, headers=auth)
        assert streamed.status_code == 413, streamed.text
        assert streamed.json() == {"error": "request body too large"}
        assert streamed.headers["x-frame-options"] == "DENY"
        ok = client.post("/api/v1/echo", json={"a": 1}, headers=auth)
        assert ok.status_code == 200
        assert 'status="413"' in client.get("/metrics").text


def test_error_envelope(config: KarrConfig) -> None:
    app = create_app(config, bootstrap=False, spa=False)

    @app.get("/api/v1/boom")
    async def boom() -> None:
        raise ApiError(409, "already exists")

    @app.get("/api/v1/crash")
    async def crash() -> None:
        raise RuntimeError("secret detail")

    with TestClient(app, raise_server_exceptions=False) as c:
        assert c.get("/api/v1/boom").json() == {"error": "already exists"}
        assert c.get("/api/v1/boom").status_code == 409
        crash_resp = c.get("/api/v1/crash")
        assert crash_resp.status_code == 500
        assert crash_resp.json() == {"error": "internal server error"}
        assert crash_resp.headers["x-frame-options"] == "DENY"
        assert 'route="/api/v1/crash",status="500"' in c.get("/metrics").text
        assert c.get("/api/v1/nope").status_code == 404
        assert c.get("/api/v1/nope").json() == {"error": "not found"}
        assert c.post("/health").status_code == 405
        assert c.post("/health").json() == {"error": "method not allowed"}
        crash_cors = c.get(
            "/api/v1/crash", headers={"Origin": "https://karr.example.com"}
        )
        assert (
            crash_cors.headers["access-control-allow-origin"]
            == "https://karr.example.com"
        )


def test_spa_fallback(tmp_path: Path) -> None:
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>karr</html>")
    (static / "assets" / "app.js").write_text("console.log(1)")
    app_for_nulls = FastAPI()
    mount_spa(app_for_nulls, static)
    with TestClient(app_for_nulls) as c:
        assert c.get("/%00").text == "<html>karr</html>"
        assert c.get("/" + "a" * 300 + "/x").text == "<html>karr</html>"
        assert c.post("/agents").status_code == 405
    (tmp_path / "secret.txt").write_text("nope")
    app = FastAPI()
    mount_spa(app, static)
    with TestClient(app) as c:
        assert c.get("/").text == "<html>karr</html>"
        assert c.get("/agents").text == "<html>karr</html>"
        assert c.get("/assets/app.js").text == "console.log(1)"
        assert c.get("/../secret.txt").text == "<html>karr</html>"
        assert c.get("/%2e%2e/secret.txt").text == "<html>karr</html>"
        assert c.get("/api/v1/agents").status_code == 404


def test_spa_without_build(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 404
    assert resp.json() == {"error": "frontend not built"}


class ThingBody(BaseModel):
    """Module-level so FastAPI can resolve the postponed annotation."""

    model_config = ConfigDict(extra="forbid")
    name: str
    url: str


def test_validation_split_400_vs_422(config: KarrConfig, auth: dict[str, str]) -> None:
    app = create_app(config, bootstrap=False, spa=False)

    @app.post("/api/v1/things", status_code=201)
    async def create(body: ThingBody) -> dict[str, str]:
        return {"name": body.name}

    with TestClient(app) as c:
        malformed = c.post(
            "/api/v1/things",
            content=b"{not json",
            headers={**auth, "Content-Type": "application/json"},
        )
        assert malformed.status_code == 400, malformed.text
        assert malformed.json() == {"error": "invalid request body"}
        missing = c.post("/api/v1/things", json={"name": "x"}, headers=auth)
        assert missing.status_code == 422 and missing.json() == {
            "error": "url is required"
        }
        extra = c.post(
            "/api/v1/things", json={"name": "x", "url": "u", "bogus": 1}, headers=auth
        )
        assert extra.status_code == 422 and extra.json() == {
            "error": "unknown field bogus"
        }
        assert (
            c.post(
                "/api/v1/things", json={"name": "x", "url": "u"}, headers=auth
            ).status_code
            == 201
        )


def test_health_routes_are_registered_before_the_spa(config: KarrConfig) -> None:
    # Regression: the bootstrap app once added the health router inside the
    # lifespan, after the SPA catch-all, so /health and /ready were 404 in
    # production. Without entering the lifespan the routes must still win.
    app = create_app(config, bootstrap=True)
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/metrics").status_code == 200
    assert client.get("/api/v1/auth/check").status_code == 401
    assert client.get("/api/v1/nope").json() == {"error": "not found"}
    for method in ("post", "put", "delete"):
        resp = getattr(client, method)("/api/v1/nope")
        assert resp.status_code == 404, method
        assert resp.json() == {"error": "not found"}
    assert client.get("/%00").status_code == 404  # no SPA build: clean 404, never a 500


def test_router_supplied_404_messages_are_kept(config: KarrConfig) -> None:
    from fastapi import HTTPException

    app = create_app(config, bootstrap=False, spa=False)

    @app.get("/api/v1/custom")
    async def custom() -> None:
        raise HTTPException(404, "agent not found")

    with TestClient(app) as c:
        assert c.get("/api/v1/custom").json() == {"error": "agent not found"}
        assert c.get("/api/v1/definitely-missing").json() == {"error": "not found"}
