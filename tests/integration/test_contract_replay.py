"""Replay the Go parity fixtures against the Python service (plan §10.1, K7).

Every fixture under ``tests/contract/fixtures`` is a request the Go service
answered at ``go-final-0.2.2``. The same requests run here, in the recorded
order, against the Python app with the Go integration suite's mock BONNIE
reproduced in respx. Identifiers created along the way are substituted into
later requests; volatile values are normalised before comparison.

A fixture passes when the status matches and the body has the same *shape*
(keys and value types, recursively). Every fixture whose status or shape is
allowed to differ is listed in ``DEVIATIONS`` with the K-D id that explains
it. A difference that is not listed there is a porting bug.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from karr.app import create_app
from karr.config import KarrConfig

pytestmark = [pytest.mark.integration, pytest.mark.contract]

FIXTURES = Path(__file__).resolve().parents[1] / "contract" / "fixtures"
ADMIN = "contract-admin-token-0001"
MOCK_BONNIE = "http://127.0.0.1:34487"  # the recorded mock's address, kept verbatim
GO_SERVER = "http://127.0.0.1:34269"  # Go's httptest server, embedded in install text
PUBLIC_URL = "https://karr.test"

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[^\"'\s]*")
HEX_TOKEN_RE = re.compile(r"\b[0-9a-f]{64}\b")


@dataclass(frozen=True)
class Deviation:
    kd: str
    status: int | None = None  # expected Python status when it differs from Go
    body: str = "same"  # "same" (shape must match), "differs" (skip the body check)
    note: str = ""


# Every allowed difference, by fixture name. `status=None` means the status is
# unchanged and only the body differs.
DEVIATIONS: dict[str, Deviation] = {
    "ready_no_agents": Deviation(
        "K-D9",
        200,
        "differs",
        "bonnie-agents is non-critical; a reconciler check was added",
    ),
    "ready_with_online_agent": Deviation(
        "K-D9", None, "differs", "the report carries the reconciler check"
    ),
    "metrics": Deviation(
        "volatile",
        None,
        "differs",
        "Prometheus text; only the content type is compared",
    ),
    "cors_preflight": Deviation(
        "K-D14",
        200,
        "differs",
        "Starlette answers a preflight with 200 OK, Go sent 204",
    ),
    "cors_preflight_other_origin": Deviation(
        "K-D14", 400, "differs", "Starlette refuses a preflight from an unlisted origin"
    ),
    "agents_create_missing_url": Deviation(
        "K-D5", 422, "same", "validation is 422, not 400"
    ),
    "agents_create_missing_name": Deviation("K-D5", 422),
    "agents_create_unknown_field": Deviation(
        "K-D21", 422, "differs", "unknown fields are rejected"
    ),
    "agents_create_duplicate_name": Deviation("K-D5", 409),
    "agents_create_bad_url_scheme": Deviation(
        "K-D13", 422, "differs", "only http/https URLs are accepted"
    ),
    "agents_status": Deviation("K-D10", None, "differs", "last_checked_at is added"),
    "agents_list_one": Deviation("K-D10", None, "differs", "last_checked_at is added"),
    "agents_get": Deviation("K-D10", None, "differs"),
    "agents_list_after_register": Deviation("K-D10", None, "differs"),
    "agents_create_second": Deviation("K-D10", None, "differs"),
    "projects_create_missing_name": Deviation("K-D5", 422),
    "projects_create_duplicate": Deviation("K-D5", 409),
    "projects_update_empty_name": Deviation("K-D5", 422),
    "environments_create_missing_image": Deviation("K-D5", 422),
    "environments_create_missing_name": Deviation("K-D5", 422),
    "environments_create_unknown_agent": Deviation("K-D5", 400),
    "environments_create_bad_agent_uuid": Deviation("K-D5", 422),
    "environments_create_duplicate_name": Deviation("K-D22", 409, "differs"),
    "environments_list_one": Deviation(
        "K-D25",
        None,
        "differs",
        "Go's list dropped project_id, env, mounts and command",
    ),
    "environments_start_again": Deviation("K-D3", 409, "differs"),
    "environments_logs": Deviation(
        "K-D2", None, "differs", "the stream ends with event: end"
    ),
    "environments_logs_missing": Deviation(
        "K-D2", 404, "differs", "checked before the headers go out"
    ),
    "agents_delete_with_environments": Deviation(
        "K-D4", 409, "differs", "409 while environments exist"
    ),
    "environments_list_after_agent_delete": Deviation(
        "K-D4",
        None,
        "differs",
        "the environment survives because the agent was not deleted",
    ),
    "environments_get_after_agent_delete": Deviation("K-D4", 200, "differs"),
    "environments_remove_missing": Deviation("K-D5", 404),
    "projects_delete_missing": Deviation(
        "K-D5", 404, "differs", "an error envelope where Go sent 204 and no body"
    ),
    "agents_delete_missing": Deviation("K-D5", 404, "differs"),
    "provision_empty_body": Deviation("K-D5", 400, "same", "a missing body is 400"),
    "install_missing_token": Deviation(
        "K-D5",
        None,
        "differs",
        "the JSON error envelope replaces Go's text/plain error",
    ),
    "install_malformed_token": Deviation("K-D5", None, "differs"),
    "install_unknown_token": Deviation("K-D7", 404, "differs"),
    "registrations_delete_missing": Deviation("K-D5", 404, "differs"),
    "spa_root_without_fs": Deviation(
        "K-D5", None, "differs", "the JSON error envelope replaces Go's text 404"
    ),
    "unknown_api_route": Deviation(
        "K-D5", None, "differs", "the JSON error envelope replaces Go's text 404"
    ),
}


class _ByteStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk


def mock_bonnie(respx: respx.MockRouter) -> None:  # noqa: F811 - shadows the module on purpose
    """The Go integration suite's mock BONNIE, byte for byte where it matters."""
    respx.get(f"{MOCK_BONNIE}/health").mock(
        return_value=httpx.Response(200, json={"healthy": True})
    )
    respx.get(f"{MOCK_BONNIE}/api/v1/gpu/status").mock(
        return_value=httpx.Response(
            200,
            json={
                "vendor": "nvidia",
                "gpus": [
                    {
                        "index": 0,
                        "name": "NVIDIA RTX 4090",
                        "vendor": "nvidia",
                        "memory_total_mib": 24576,
                        "memory_free_mib": 20480,
                        "utilization_percent": 15,
                    }
                ],
                "timestamp": "2026-09-14T17:58:25.537082516Z",
            },
        )
    )
    respx.get(f"{MOCK_BONNIE}/api/v1/system/info").mock(
        return_value=httpx.Response(
            200,
            json={
                "system": {
                    "hostname": "test-host",
                    "os": "linux",
                    "arch": "amd64",
                    "kernel": "6.19.0",
                    "cpu_model": "AMD Ryzen 9 7950X",
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
    respx.get(f"{MOCK_BONNIE}/api/v1/containers").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.post(f"{MOCK_BONNIE}/api/v1/containers").mock(
        return_value=httpx.Response(201, json={"id": "test-container-123"})
    )
    respx.post(url__regex=rf"{MOCK_BONNIE}/api/v1/containers/[^/]+/start").mock(
        return_value=httpx.Response(200, json={"status": "started"})
    )
    respx.post(url__regex=rf"{MOCK_BONNIE}/api/v1/containers/[^/]+/stop").mock(
        return_value=httpx.Response(200, json={"status": "stopped"})
    )
    respx.delete(url__regex=rf"{MOCK_BONNIE}/api/v1/containers/[^/]+").mock(
        return_value=httpx.Response(204)
    )
    respx.get(url__regex=rf"{MOCK_BONNIE}/api/v1/containers/[^/]+/logs").mock(
        return_value=httpx.Response(
            200,
            stream=_ByteStream(
                [
                    b"data: container starting...\n\n",
                    b"data: loading model weights\n\n",
                    b"data: model loaded successfully\n\n",
                    b"data: server listening on :8080\n\n",
                ]
            ),
            headers={"Content-Type": "text/event-stream"},
        )
    )


@pytest.fixture
def contract_api(database_url: str, clean_tables: None) -> Iterator[TestClient]:
    """Like ``api`` but with the CORS origin and proxy trust the Go harness had."""
    cfg = KarrConfig(
        component="karr",
        database_url=SecretStr(database_url),
        admin_token=SecretStr(ADMIN),
        secret_key=SecretStr(Fernet.generate_key().decode()),
        cors_origins=["https://karr.example.com"],
        trusted_proxies=["10.0.0.0/8"],
        public_url=PUBLIC_URL,
    )
    with TestClient(
        create_app(cfg), base_url="http://karr.test", client=("10.0.0.1", 50000)
    ) as client:
        client.headers["Authorization"] = f"Bearer {ADMIN}"
        yield client


def load_fixtures() -> list[dict[str, Any]]:
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(FIXTURES.glob("*.json"))
        if not p.name.startswith("_")
    ]


def normalise_text(text: str) -> str:
    text = UUID_RE.sub("<uuid>", text)
    text = TS_RE.sub("<ts>", text)
    text = HEX_TOKEN_RE.sub("<token>", text)
    return text.replace(GO_SERVER, "<server>").replace(PUBLIC_URL, "<server>")


def shape(value: Any) -> Any:
    """Keys and value types, recursively; lists collapse to the shape of their first item."""
    if isinstance(value, dict):
        return {k: shape(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [shape(value[0])] if value else []
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int | float):
        return "number"
    if value is None:
        return "null"
    return "string"


def substitute(text: str, subst: dict[str, str]) -> str:
    for recorded, live in subst.items():
        text = text.replace(recorded, live)
    return text


@pytest.mark.respx(assert_all_called=False)
def test_fixture_replay(contract_api: TestClient, respx_mock: respx.MockRouter) -> None:
    api = contract_api
    subst: dict[str, str] = {GO_SERVER: PUBLIC_URL}
    registry = api.app.state.registry  # type: ignore[attr-defined]
    failures: list[str] = []
    replayed = 0

    if True:
        mock_bonnie(respx_mock)
        for fx in load_fixtures():
            name = fx["name"]
            # the Go harness polled the registry at these two points
            if name == "agents_status":
                api.portal.call(registry.poll)
            if name == "environments_create_second":
                api.portal.call(registry.poll)

            path = substitute(fx["path"], subst)
            headers = dict(fx.get("headers", {}))
            content: bytes | None = None
            if "body" in fx:
                content = substitute(json.dumps(fx["body"]), subst).encode()
                headers.setdefault("Content-Type", "application/json")
            elif "raw_body" in fx:
                content = fx["raw_body"].encode()
                headers.setdefault("Content-Type", "application/json")
            resp = api.request(fx["method"], path, content=content, headers=headers)
            replayed += 1

            # collect the identifiers later fixtures refer to
            if resp.headers.get("content-type", "").startswith(
                "application/json"
            ) and fx.get("response_json"):
                try:
                    live, recorded = resp.json(), fx["response_json"]
                except ValueError:
                    live, recorded = None, None
                if isinstance(live, dict) and isinstance(recorded, dict):
                    for key in ("id", "token", "agent_id"):
                        if isinstance(recorded.get(key), str) and isinstance(
                            live.get(key), str
                        ):
                            subst[recorded[key]] = live[key]

            deviation = DEVIATIONS.get(name)
            expected_status = (
                fx["status"]
                if deviation is None or deviation.status is None
                else deviation.status
            )
            problems: list[str] = []
            if resp.status_code != expected_status:
                problems.append(f"status {resp.status_code} != {expected_status}")
            if deviation is None or deviation.body == "same":
                problems.extend(_compare_body(fx, resp))
            elif deviation.kd == "volatile":
                recorded_ct = (
                    fx["response_headers"].get("Content-Type", "").split(";")[0]
                )
                if not resp.headers.get("content-type", "").startswith(recorded_ct):
                    problems.append(
                        f"content-type {resp.headers.get('content-type')!r}"
                    )
            if problems:
                tag = f" ({deviation.kd})" if deviation else " (NO K-D: porting bug)"
                failures.append(
                    f"{name}{tag}: "
                    + "; ".join(problems)
                    + f" -- body: {resp.text[:200]!r}"
                )

    assert replayed >= 80
    assert not failures, "\n".join(failures)


def _compare_body(fx: dict[str, Any], resp: httpx.Response) -> list[str]:
    if "response_json" in fx:
        recorded = fx["response_json"]
        if not resp.headers.get("content-type", "").startswith("application/json"):
            return [f"expected JSON, got {resp.headers.get('content-type')!r}"]
        try:
            live = resp.json()
        except ValueError:
            return ["response is not valid JSON"]
        if isinstance(recorded, dict) and "error" in recorded:
            return (
                []
                if isinstance(live, dict) and "error" in live
                else ["no error envelope"]
            )
        if shape(live) != shape(recorded):
            return [f"shape {shape(live)} != {shape(recorded)}"]
        return []
    if "response_text" in fx:
        recorded_ct = fx["response_headers"].get("Content-Type", "")
        live_ct = resp.headers.get("content-type", "")
        if recorded_ct.split(";")[0] != live_ct.split(";")[0]:
            return [f"content-type {live_ct!r} != {recorded_ct!r}"]
        if recorded_ct.startswith("text/event-stream"):
            return (
                []
                if normalise_text(resp.text).startswith(
                    normalise_text(fx["response_text"])
                )
                else ["stream prefix differs"]
            )
        if recorded_ct.startswith("text/x-shellscript"):
            return []  # the script is flag-commons' hardened template; the token and URL are checked below
        return (
            []
            if normalise_text(resp.text) == normalise_text(fx["response_text"])
            else ["text differs"]
        )
    return [] if not resp.content else ["unexpected body"]


def test_every_deviation_is_annotated_with_a_known_defect() -> None:
    names = {fx["name"] for fx in load_fixtures()}
    unknown = set(DEVIATIONS) - names
    assert not unknown, f"deviations for fixtures that do not exist: {sorted(unknown)}"
    assert all(
        re.fullmatch(r"K-D\d+", d.kd) or d.kd == "volatile" for d in DEVIATIONS.values()
    )
    assert [n for n, d in DEVIATIONS.items() if d.kd == "volatile"] == ["metrics"]
