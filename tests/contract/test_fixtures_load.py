"""The recorded Go fixtures must stay well-formed; replay lands with K7."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

pytestmark = pytest.mark.contract


def test_fixtures_present_and_well_formed() -> None:
    files = sorted(p for p in FIXTURES.glob("*.json") if not p.name.startswith("_"))
    assert len(files) >= 80
    for path in files:
        data = json.loads(path.read_text())
        assert {"name", "method", "path", "status"} <= set(data)
        assert data["method"] in {"GET", "POST", "PUT", "DELETE", "OPTIONS"}
        assert 200 <= data["status"] < 600


def test_every_route_is_covered() -> None:
    paths = {
        json.loads(p.read_text())["path"]
        for p in FIXTURES.glob("*.json")
        if not p.name.startswith("_")
    }
    for prefix in (
        "/health",
        "/ready",
        "/metrics",
        "/api/v1/agents",
        "/api/v1/projects",
        "/api/v1/environments",
        "/api/v1/install.sh",
        "/api/v1/agents/register",
        "/api/v1/agents/provision",
        "/api/v1/agents/registrations",
    ):
        assert any(p.startswith(prefix) for p in paths), prefix
