from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from karr.api.errors import ApiError
from karr.api.schemas import AgentOut, EnvironmentOut, ProjectUpdate, rfc3339
from karr.services.common import parse_uuid, validate_agent_url


def test_rfc3339() -> None:
    assert (
        rfc3339(datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc))
        == "2026-09-14T12:00:00Z"
    )
    assert (
        rfc3339(datetime(2026, 9, 14, 12, 0, 0, 123456, tzinfo=timezone.utc))
        == "2026-09-14T12:00:00.123456Z"
    )
    assert (
        rfc3339(datetime(2026, 9, 14, 12, 0, 0)) == "2026-09-14T12:00:00Z"
    )  # naive → UTC
    assert rfc3339(None) is None


def test_agent_out_never_has_a_token() -> None:
    now = datetime.now(timezone.utc)

    class Row:
        id = uuid.uuid4()
        name = "gpu"
        url = "http://gpu:7777"
        status = "offline"
        last_seen_at = None
        last_checked_at = now
        created_at = now
        updated_at = now
        token_encrypted = "gAAAA-secret"

    data = AgentOut.model_validate(Row()).model_dump(mode="json")
    assert "token" not in data and "token_encrypted" not in data
    assert data["last_seen_at"] is None and data["last_checked_at"].endswith("Z")


def test_environment_out_defaults() -> None:
    now = datetime.now(timezone.utc)
    out = EnvironmentOut(
        id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        name="e",
        image="i",
        status="creating",
        gpu=False,
        created_at=now,
        updated_at=now,
    )
    data = out.model_dump(mode="json")
    assert (
        data["project_id"] is None and data["env"] == [] and data["container_id"] == ""
    )


def test_project_update_distinguishes_absent_from_empty() -> None:
    assert ProjectUpdate().model_dump(exclude_unset=True) == {}
    assert ProjectUpdate(name="").model_dump(exclude_unset=True) == {"name": ""}
    assert ProjectUpdate(description=None).model_dump(exclude_unset=True) == {
        "description": None
    }


@pytest.mark.parametrize(
    "url", ["http://gpu:7777", "https://gpu.example/", "http://192.168.1.5:7777/base/"]
)
def test_validate_agent_url_ok(url: str) -> None:
    assert validate_agent_url(" " + url + " ") == url.strip().rstrip("/")


@pytest.mark.parametrize(
    "url",
    ["", "gpu:7777", "ftp://gpu", "file:///etc/passwd", "http://", "http://u:p@gpu"],
)
def test_validate_agent_url_rejects(url: str) -> None:
    with pytest.raises(ApiError) as info:
        validate_agent_url(url)
    assert info.value.status_code == 422


def test_parse_uuid() -> None:
    value = uuid.uuid4()
    assert parse_uuid(str(value), "agent") == value
    with pytest.raises(ApiError) as info:
        parse_uuid("nope", "agent")
    assert (info.value.status_code, info.value.message) == (400, "invalid agent id")
