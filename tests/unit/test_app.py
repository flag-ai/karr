from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

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
    assert "frame-ancestors 'none'" in resp.headers["content-security-policy"]
    assert "strict-transport-security" not in resp.headers


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


def test_body_limit(client: TestClient, auth: dict[str, str]) -> None:
    resp = client.post(
        "/api/v1/auth/check", headers={**auth, "Content-Length": "2000000"}
    )
    assert resp.status_code == 413
    assert resp.json() == {"error": "request body too large"}


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
        assert c.get("/api/v1/nope").status_code == 404
        assert c.get("/api/v1/nope").json() == {"error": "not found"}
        assert c.post("/health").status_code == 405
        assert c.post("/health").json() == {"error": "method not allowed"}


def test_spa_fallback(tmp_path: Path) -> None:
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>karr</html>")
    (static / "assets" / "app.js").write_text("console.log(1)")
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
