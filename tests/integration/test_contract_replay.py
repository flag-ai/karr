"""Replay the Go parity fixtures against the Python service (plan §10.1, K7).

Every fixture under ``tests/contract/fixtures`` is a request the Go service
answered at ``go-final-0.2.2``. The same requests run here, in the recorded
order, against the Python app with the Go integration suite's mock BONNIE
reproduced in respx. Identifiers created along the way are substituted into
later requests; volatile values are normalised.

A fixture passes when the status matches, the content type matches, the body
has the same *shape* (keys and value types, recursively) and the contract
fields listed in ``VALUE_FIELDS`` carry the same values. Every fixture whose
result is allowed to differ is listed in ``DEVIATIONS`` with the K-D id that
explains it (or ``framework``/``volatile`` for the two non-defect cases). A
difference that is not listed there is a porting bug. Two invariants hold for
every response regardless: no secret sent to the service comes back in a
body, and no error body carries internal detail.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from karr.app import create_app, mount_spa
from karr.config import KarrConfig

pytestmark = [pytest.mark.integration, pytest.mark.contract]

FIXTURES = Path(__file__).resolve().parents[1] / "contract" / "fixtures"
FIXTURE_COUNT = 87
MOCK_BONNIE = "http://127.0.0.1:34487"  # the recorded mock's address, kept verbatim
GO_SERVER = "http://127.0.0.1:34269"  # Go's httptest server, embedded in install text
PUBLIC_URL = "https://karr.test"
# secrets the fixtures send in; none may ever appear in a response body
REQUEST_SECRETS = ("agent-secret", "agent-auth")
INTERNAL_DETAIL = re.compile(
    r"Traceback|postgresql(\+psycopg)?://|sqlalchemy|psycopg|File \"", re.I
)

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[^\"'\s]*")
HEX_TOKEN_RE = re.compile(r"\b[0-9a-f]{64}\b")
VERSION_RE = re.compile(
    r"[^\s\"']+ \(commit: [^)]*, built: [^)]*\)"
)  # build info is volatile

# fields whose *values* must match Go once ids, timestamps and tokens are normalised
VALUE_FIELDS = frozenset(
    {
        "status",
        "name",
        "url",
        "image",
        "container_id",
        "gpu",
        "label",
        "message",
        "install_command",
        "description",
        "healthy",
        "version",
    }
)
SCRIPT_MARKERS = (
    "set -euo pipefail\n",
    "chmod 700 ",
    "chmod 640 ",
    "[Unit]",
    "[Service]",
    "NoNewPrivileges=true",
    "ProtectSystem=strict",
    "SERVER_URL=https://karr.test\n",
)


@dataclass(frozen=True)
class Deviation:
    kd: str
    status: int | None = None  # expected Python status when it differs from Go
    body: str = "same"  # "same", "superset" (recorded keys are a subset), "differs" (body skipped)
    note: str = ""
    content_type: bool = True  # False when the media type itself changed
    ignore_values: frozenset[str] = field(default_factory=frozenset)


# Every allowed difference, by fixture name. `status=None` means the status is
# unchanged and only the body differs.
DEVIATIONS: dict[str, Deviation] = {
    "ready_no_agents": Deviation(
        "K-D9",
        200,
        "superset",
        "bonnie-agents is non-critical",
        ignore_values=frozenset({"healthy"}),
    ),
    "ready_with_online_agent": Deviation(
        "K-D9", None, "superset", "the report carries the reconciler check"
    ),
    "metrics": Deviation(
        "volatile",
        None,
        "differs",
        "Prometheus text; only the content type is compared",
    ),
    "cors_preflight": Deviation(
        "framework",
        200,
        "differs",
        "Starlette answers a preflight with 200 OK, Go sent 204",
        content_type=False,
    ),
    "cors_preflight_other_origin": Deviation(
        "framework",
        400,
        "differs",
        "Starlette refuses a preflight from an unlisted origin",
        content_type=False,
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
    "agents_status": Deviation("K-D10", None, "superset", "last_checked_at is added"),
    "agents_list_one": Deviation("K-D10", None, "superset"),
    "agents_get": Deviation("K-D10", None, "superset"),
    "agents_list_after_register": Deviation(
        "K-D13",
        None,
        "superset",
        "Go had also kept gpu-02 (ftp://x), so the recorded rows differ",
        ignore_values=frozenset({"name", "url", "status"}),
    ),
    "agents_create_second": Deviation("K-D10", None, "superset"),
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
        "superset",
        "Go's list dropped project_id, env, mounts and command; its first row is "
        "the duplicate env-1 that K-D22 now refuses",
        ignore_values=frozenset({"image", "gpu"}),
    ),
    "environments_start_again": Deviation("K-D3", 409, "differs", content_type=False),
    "environments_logs": Deviation(
        "K-D2",
        None,
        "same",
        "the stream ends with event: end; the recorded frames are a prefix",
    ),
    "environments_logs_missing": Deviation(
        "K-D2", 404, "differs", "checked before the headers go out", content_type=False
    ),
    "agents_delete_with_environments": Deviation(
        "K-D4", 409, "differs", "409 while environments exist", content_type=False
    ),
    "environments_list_after_agent_delete": Deviation(
        "K-D4",
        None,
        "differs",
        "the environment survives because the agent was not deleted",
    ),
    "environments_get_after_agent_delete": Deviation(
        "K-D4", 200, "differs", content_type=False
    ),
    "environments_remove_missing": Deviation("K-D5", 404),
    "projects_delete_missing": Deviation(
        "K-D5",
        404,
        "differs",
        "an error envelope where Go sent 204 and no body",
        content_type=False,
    ),
    "agents_delete_missing": Deviation("K-D5", 404, "differs", content_type=False),
    "provision": Deviation(
        "K-D26",
        None,
        "same",
        "install_command ends with `bash -s --` so --address passes the pipe",
        ignore_values=frozenset({"install_command"}),
    ),
    "install_missing_token": Deviation(
        "K-D5",
        None,
        "differs",
        "the JSON error envelope replaces Go's text/plain error",
        content_type=False,
    ),
    "install_malformed_token": Deviation("K-D5", None, "differs", content_type=False),
    "install_unknown_token": Deviation("K-D7", 404, "differs", content_type=False),
    "registrations_delete_missing": Deviation(
        "K-D5", 404, "differs", content_type=False
    ),
    "spa_root_without_fs": Deviation(
        "K-D5",
        None,
        "differs",
        "the JSON error envelope replaces Go's text 404",
        content_type=False,
    ),
    "unknown_api_route": Deviation(
        "K-D5",
        None,
        "differs",
        "the JSON error envelope replaces Go's text 404",
        content_type=False,
    ),
}
NON_DEFECT_KDS = {
    "volatile": {"metrics"},
    "framework": {"cors_preflight", "cors_preflight_other_origin"},
}


class _ByteStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk


def mock_bonnie(router: respx.MockRouter) -> dict[str, respx.Route]:
    """The Go integration suite's mock BONNIE, byte for byte where it matters."""
    routes = {
        "health": router.get(f"{MOCK_BONNIE}/health").mock(
            return_value=httpx.Response(200, json={"healthy": True})
        ),
        "gpu": router.get(f"{MOCK_BONNIE}/api/v1/gpu/status").mock(
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
        ),
        "system": router.get(f"{MOCK_BONNIE}/api/v1/system/info").mock(
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
        ),
        "list": router.get(f"{MOCK_BONNIE}/api/v1/containers").mock(
            return_value=httpx.Response(200, json=[])
        ),
        "create": router.post(f"{MOCK_BONNIE}/api/v1/containers").mock(
            return_value=httpx.Response(201, json={"id": "test-container-123"})
        ),
        "start": router.post(
            url__regex=rf"{MOCK_BONNIE}/api/v1/containers/[^/]+/start"
        ).mock(return_value=httpx.Response(200, json={"status": "started"})),
        "stop": router.post(
            url__regex=rf"{MOCK_BONNIE}/api/v1/containers/[^/]+/stop"
        ).mock(return_value=httpx.Response(200, json={"status": "stopped"})),
        "remove": router.delete(
            url__regex=rf"{MOCK_BONNIE}/api/v1/containers/[^/]+"
        ).mock(return_value=httpx.Response(204)),
        # respx hands back this same Response for every match, so the stream can be
        # consumed once; the only other logs fixture 404s before it is reached
        "logs": router.get(
            url__regex=rf"{MOCK_BONNIE}/api/v1/containers/[^/]+/logs"
        ).mock(
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
        ),
    }
    return routes


@pytest.fixture
def contract_api(
    live_config: KarrConfig, clean_tables: None, tmp_path: Path
) -> Iterator[TestClient]:
    """Like ``api`` but with the Go harness's CORS origin and no SPA build (hermetic)."""
    cfg = live_config.model_copy(update={"cors_origins": ["https://karr.example.com"]})
    app = create_app(cfg, spa=False)
    mount_spa(
        app, tmp_path / "no-static"
    )  # `GET /` must 404 whatever the working tree holds
    with TestClient(
        app, base_url="http://karr.test", client=("10.0.0.1", 50000)
    ) as client:
        client.headers["Authorization"] = f"Bearer {cfg.admin_token.get_secret_value()}"
        yield client


def load_fixtures() -> list[dict[str, Any]]:
    files = sorted(p for p in FIXTURES.glob("*.json") if not p.name.startswith("_"))
    assert len(files) == FIXTURE_COUNT, (
        "a fixture was added or removed: update FIXTURE_COUNT deliberately"
    )
    return [json.loads(p.read_text(encoding="utf-8")) for p in files]


def normalise_text(text: str) -> str:
    text = UUID_RE.sub("<uuid>", text)
    text = TS_RE.sub("<ts>", text)
    text = HEX_TOKEN_RE.sub("<token>", text)
    text = VERSION_RE.sub("<version>", text)
    return text.replace(GO_SERVER, "<server>").replace(PUBLIC_URL, "<server>")


def normalise_value(value: Any) -> Any:
    return normalise_text(value) if isinstance(value, str) else value


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


def is_superset(live: Any, recorded: Any) -> bool:
    """Every recorded key exists in live with the same shape; live may add keys."""
    if isinstance(recorded, dict):
        return isinstance(live, dict) and all(
            k in live and is_superset(live[k], v) for k, v in recorded.items()
        )
    if isinstance(recorded, list):
        return isinstance(live, list) and (
            not recorded or (bool(live) and is_superset(live[0], recorded[0]))
        )
    return shape(live) == shape(recorded)


def value_mismatches(
    live: Any, recorded: Any, ignore: frozenset[str], path: str = ""
) -> list[str]:
    """Contract fields must carry the same (normalised) values, recursively."""
    out: list[str] = []
    if isinstance(recorded, dict) and isinstance(live, dict):
        for k, v in recorded.items():
            if k not in live:
                continue
            if k in VALUE_FIELDS and k not in ignore and not isinstance(v, dict | list):
                if normalise_value(live[k]) != normalise_value(v):
                    out.append(f"{path}{k}: {live[k]!r} != {v!r}")
            else:
                out.extend(value_mismatches(live[k], v, ignore, f"{path}{k}."))
    elif isinstance(recorded, list) and isinstance(live, list):
        for i, (lv, rv) in enumerate(zip(live, recorded, strict=False)):
            out.extend(value_mismatches(lv, rv, ignore, f"{path}[{i}]."))
    return out


def substitute(text: str, subst: dict[str, str]) -> str:
    for recorded, live in subst.items():
        text = text.replace(recorded, live)
    return text


@pytest.mark.timeout(180)
@pytest.mark.respx(assert_all_called=False)
def test_fixture_replay(contract_api: TestClient, respx_mock: respx.MockRouter) -> None:
    api = contract_api
    admin = api.headers["Authorization"].removeprefix("Bearer ")
    subst: dict[str, str] = {GO_SERVER: PUBLIC_URL}
    registry = api.app.state.registry  # type: ignore[attr-defined]
    routes = mock_bonnie(respx_mock)
    failures: list[str] = []
    live_tokens: set[str] = set()
    replayed = 0

    for fx in load_fixtures():
        name = fx["name"]
        # the Go harness polled the registry at these two points
        if name in ("agents_status", "environments_create_second"):
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

        live_json: Any = None
        if resp.headers.get("content-type", "").startswith("application/json"):
            try:
                live_json = resp.json()
            except ValueError:
                live_json = None
        # collect the identifiers later fixtures refer to
        recorded_json = fx.get("response_json")
        if isinstance(live_json, dict) and isinstance(recorded_json, dict):
            for key in ("id", "token", "agent_id"):
                rv, lv = recorded_json.get(key), live_json.get(key)
                if isinstance(rv, str) and isinstance(lv, str) and len(rv) >= 8:
                    subst[rv] = lv
                    if key == "token":
                        live_tokens.add(lv)

        problems: list[str] = []
        # invariants that hold for every response
        for secret in (admin, *REQUEST_SECRETS):
            if secret in resp.text:
                problems.append(f"secret {secret[:6]}… appears in the response")
        for tok in HEX_TOKEN_RE.findall(resp.text):
            if tok not in live_tokens:
                problems.append(
                    "a token other than the live registration token appears in the response"
                )
        if resp.status_code >= 400 and INTERNAL_DETAIL.search(resp.text):
            problems.append("error body carries internal detail")

        deviation = DEVIATIONS.get(name)
        expected_status = (
            fx["status"]
            if deviation is None or deviation.status is None
            else deviation.status
        )
        if resp.status_code != expected_status:
            problems.append(f"status {resp.status_code} != {expected_status}")
        if deviation is None or deviation.content_type:
            recorded_ct = fx["response_headers"].get("Content-Type", "").split(";")[0]
            live_ct = resp.headers.get("content-type", "").split(";")[0]
            if recorded_ct != live_ct:
                problems.append(f"content-type {live_ct!r} != {recorded_ct!r}")
        mode = "same" if deviation is None else deviation.body
        if mode != "differs":
            problems.extend(
                _compare_body(
                    fx,
                    resp,
                    live_json,
                    mode,
                    deviation.ignore_values if deviation else frozenset(),
                    subst,
                )
            )
        if name == "agents_status":
            for key in ("system", "gpu"):
                if not routes[key].called:
                    problems.append(
                        f"BONNIE {key} was never fetched: the status is not live"
                    )
        if name == "install_ok":
            live_token = next(iter(live_tokens), "")
            if f"REGISTRATION_TOKEN={live_token}\n" not in resp.text:
                problems.append(
                    "the install script does not carry the provisioned token"
                )
            problems.extend(
                f"install script lacks {m!r}"
                for m in SCRIPT_MARKERS
                if m not in resp.text
            )
        if problems:
            tag = f" ({deviation.kd})" if deviation else " (NO K-D: porting bug)"
            failures.append(
                f"{name}{tag}: "
                + "; ".join(problems)
                + f" -- body: {resp.text[:200]!r}"
            )

    assert replayed == FIXTURE_COUNT
    assert not failures, "\n".join(failures)


def _compare_body(
    fx: dict[str, Any],
    resp: httpx.Response,
    live: Any,
    mode: str,
    ignore: frozenset[str],
    subst: dict[str, str],
) -> list[str]:
    if "response_json" in fx:
        recorded = fx["response_json"]
        if live is None:
            return [f"expected JSON, got {resp.headers.get('content-type')!r}"]
        if isinstance(recorded, dict) and "error" in recorded:
            return (
                []
                if isinstance(live, dict) and "error" in live
                else ["no error envelope"]
            )
        if mode == "superset":
            if not is_superset(live, recorded):
                return [f"live {shape(live)} is not a superset of {shape(recorded)}"]
        elif shape(live) != shape(recorded):
            return [f"shape {shape(live)} != {shape(recorded)}"]
        return value_mismatches(live, recorded, ignore)
    if "response_text" in fx:
        recorded_ct = fx["response_headers"].get("Content-Type", "")
        if recorded_ct.startswith("text/event-stream"):
            return (
                []
                if normalise_text(resp.text).startswith(
                    normalise_text(fx["response_text"])
                )
                else ["stream prefix differs"]
            )
        if recorded_ct.startswith("text/x-shellscript"):
            return []  # the script is checked line by line in the replay loop (SCRIPT_MARKERS)
        return (
            []
            if normalise_text(resp.text) == normalise_text(fx["response_text"])
            else ["text differs"]
        )
    del subst
    return [] if not resp.content else ["unexpected body"]


def test_every_deviation_is_annotated_with_a_known_defect() -> None:
    names = {fx["name"] for fx in load_fixtures()}
    unknown = set(DEVIATIONS) - names
    assert not unknown, f"deviations for fixtures that do not exist: {sorted(unknown)}"
    known_kds = {f"K-D{i}" for i in range(1, 27)}
    for name, dev in DEVIATIONS.items():
        if dev.kd in NON_DEFECT_KDS:
            assert name in NON_DEFECT_KDS[dev.kd], f"{name} is not a {dev.kd} case"
        else:
            assert dev.kd in known_kds, (
                f"{name}: {dev.kd} is not in the plan's defect table"
            )
