"""Projects CRUD (routes 14–18) against the live database."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration
ZERO = "00000000-0000-0000-0000-000000000000"


def test_projects_crud(api: TestClient) -> None:
    assert api.get("/api/v1/projects").json() == []
    created = api.post(
        "/api/v1/projects",
        json={"name": " llm-eval ", "description": "Evaluation runs"},
    )
    assert created.status_code == 201, created.text
    project = created.json()
    assert project["name"] == "llm-eval" and project["description"] == "Evaluation runs"
    assert project["created_at"].endswith("Z")
    pid = project["id"]

    assert (
        api.post("/api/v1/projects", json={"name": "llm-eval"}).status_code == 409
    )  # K-D5
    assert api.post("/api/v1/projects", json={"name": "  "}).status_code == 422
    assert api.post("/api/v1/projects", json={"description": "x"}).status_code == 422
    assert (
        api.post("/api/v1/projects", json={"name": "x", "bogus": 1}).status_code == 422
    )  # K-D21
    assert (
        api.post(
            "/api/v1/projects",
            content=b"{",
            headers={"Content-Type": "application/json"},
        ).status_code
        == 400
    )

    assert [p["id"] for p in api.get("/api/v1/projects").json()] == [pid]
    assert api.get(f"/api/v1/projects/{pid}").json()["name"] == "llm-eval"
    assert api.get(f"/api/v1/projects/{ZERO}").json() == {"error": "project not found"}
    assert api.get("/api/v1/projects/not-a-uuid").json() == {
        "error": "invalid project id"
    }

    updated = api.put(f"/api/v1/projects/{pid}", json={"description": "Updated"})
    assert updated.status_code == 200 and updated.json()["name"] == "llm-eval"
    assert updated.json()["description"] == "Updated"
    renamed = api.put(f"/api/v1/projects/{pid}", json={"name": "llm-eval-2"})
    assert (
        renamed.json()["name"] == "llm-eval-2"
        and renamed.json()["description"] == "Updated"
    )
    assert (
        api.put(f"/api/v1/projects/{pid}", json={"name": ""}).status_code == 422
    )  # K-D5 (Go: 500)
    other = api.post("/api/v1/projects", json={"name": "other"}).json()
    assert (
        api.put(
            f"/api/v1/projects/{other['id']}", json={"name": "llm-eval-2"}
        ).status_code
        == 409
    )
    assert api.put(f"/api/v1/projects/{ZERO}", json={"name": "x"}).status_code == 404

    assert api.delete(f"/api/v1/projects/{pid}").status_code == 204
    assert api.delete(f"/api/v1/projects/{pid}").status_code == 404  # K-D5 (Go: 204)
    assert api.delete("/api/v1/projects/nope").status_code == 400


def test_projects_require_admin(api: TestClient) -> None:
    api.headers.pop("Authorization")
    assert api.get("/api/v1/projects").status_code == 401
    assert api.post("/api/v1/projects", json={"name": "x"}).status_code == 401
