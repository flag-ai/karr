from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from flag_commons.bonnie import BonnieError

from karr.services import reconcile as mod
from karr.services.reconcile import Reconciler, ReconcilerChecker, reconcile_once

pytestmark = pytest.mark.anyio


@dataclass
class _Agent:
    id: str
    name: str
    status: str = "online"


class _Client:
    def __init__(self, behaviour: str) -> None:
        self.behaviour = behaviour

    async def list_containers(self) -> list[Any]:
        if self.behaviour == "hang":
            await asyncio.sleep(5)
        if self.behaviour == "bonnie-error":
            raise BonnieError("docker down")
        if self.behaviour == "crash":
            raise RuntimeError("boom")
        return []


class _Registry:
    def __init__(self, clients: dict[str, _Client]) -> None:
        self._clients = clients

    def agents(self) -> list[_Agent]:
        return [_Agent(id=k, name=f"agent-{k}") for k in self._clients] + [
            _Agent(id="off", name="offline-one", status="offline")
        ]

    def get(self, agent_id: str) -> _Client | None:
        return self._clients.get(agent_id)


class _Session:
    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


class _FakeService:
    """Stands in for EnvironmentService: one change per agent, or a slow DB write."""

    slow: set[str] = set()

    def __init__(self, session: object, registry: object) -> None:
        pass

    async def reconcile_agent(self, agent_id: uuid.UUID, containers: list[Any]) -> int:
        if str(agent_id) in self.slow:
            await asyncio.sleep(5)
        return 1


@pytest.fixture
def fake_service(monkeypatch: pytest.MonkeyPatch) -> type[_FakeService]:
    _FakeService.slow = set()
    monkeypatch.setattr(mod, "EnvironmentService", _FakeService)
    return _FakeService


def _ids(n: int) -> list[str]:
    return [str(uuid.uuid4()) for _ in range(n)]


async def test_pass_isolates_failures_and_timeouts(
    fake_service: type[_FakeService], caplog: pytest.LogCaptureFixture
) -> None:
    ok, hang, err, crash, slow_db = _ids(5)
    registry = _Registry(
        {
            ok: _Client("ok"),
            hang: _Client("hang"),
            err: _Client("bonnie-error"),
            crash: _Client("crash"),
            slow_db: _Client("ok"),
        }
    )
    fake_service.slow = {slow_db}
    with caplog.at_level("WARNING"):
        changed = await reconcile_once(_Session, registry, per_agent_timeout=0.05)  # type: ignore[arg-type]
    assert changed == 1  # only the healthy agent counted; the offline one was skipped
    timeouts = [r for r in caplog.records if "exceeded" in r.getMessage()]
    assert len(timeouts) == 2  # the hanging BONNIE call and the slow database write
    assert any("boom" in r.getMessage() for r in caplog.records)


async def test_pass_runs_agents_concurrently(fake_service: type[_FakeService]) -> None:
    ids = _ids(6)
    registry = _Registry({i: _Client("hang") for i in ids})
    loop = asyncio.get_running_loop()
    start = loop.time()
    await reconcile_once(_Session, registry, per_agent_timeout=0.05, concurrency=3)  # type: ignore[arg-type]
    elapsed = loop.time() - start
    assert 0.08 < elapsed < 0.5  # two batches of three, not six sequential timeouts


async def test_checker_reports_a_stalled_loop(fake_service: type[_FakeService]) -> None:
    registry = _Registry({})
    r = Reconciler(_Session, registry, interval=0.01, per_agent_timeout=0.01)  # type: ignore[arg-type]
    checker = ReconcilerChecker(r)
    with pytest.raises(RuntimeError, match="not started"):
        checker.check()
    r.start()
    try:
        await asyncio.sleep(0.05)
        checker.check()  # passes are completing
        assert r.last_success_at is not None
        r.last_success_at -= 10  # pretend the last pass was long ago
        r.started_at -= 10  # type: ignore[operator]
        with pytest.raises(RuntimeError, match="no completed reconcile pass"):
            checker.check()
    finally:
        await r.stop()
