"""Boot the real app (lifespan included) against PostgreSQL."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from karr.app import create_app
from karr.config import KarrConfig

pytestmark = pytest.mark.integration


def test_lifespan_boots_and_health_routes_win_over_spa(live_config: KarrConfig) -> None:
    app = create_app(live_config)
    with TestClient(app, base_url="http://karr.test") as client:
        health = client.get("/health")
        assert health.status_code == 200, health.text
        assert health.json()["status"] == "ok"
        ready = client.get("/ready")
        assert ready.status_code == 200, ready.text
        names = [c["name"] for c in ready.json()["checks"]]
        assert "database" in names
        assert app.state.engine is not None
        assert client.get("/api/v1/auth/check").status_code == 401
    # disposed on shutdown: a new connection attempt would need a new engine
    assert app.state.engine.pool.status()  # pool object still inspectable


def test_lifespan_fails_cleanly_on_bad_database(live_config: KarrConfig) -> None:
    from flag_commons.database import DatabaseError
    from pydantic import SecretStr

    bad = live_config.model_copy(
        update={"database_url": SecretStr("postgresql://nobody:wrong@127.0.0.1:1/none")}
    )
    app = create_app(bad)
    with pytest.raises(DatabaseError), TestClient(app):
        pass
