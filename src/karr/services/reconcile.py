"""Background reconciliation of environment status against BONNIE (K-D3)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid

from flag_commons.bonnie import STATUS_ONLINE, AgentRegistry, BonnieError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from karr.api.sse import StreamSlots
from karr.services.environments import EnvironmentService

DEFAULT_RECONCILE_INTERVAL = 30.0
DEFAULT_PER_AGENT_TIMEOUT = 20.0
DEFAULT_CONCURRENCY = 4  # agents reconciled at once; each holds one DB session
MISSED_PASSES_BEFORE_UNHEALTHY = 3

_log = logging.getLogger(__name__)


async def reconcile_once(
    sessions: async_sessionmaker[AsyncSession],
    registry: AgentRegistry,
    *,
    per_agent_timeout: float = DEFAULT_PER_AGENT_TIMEOUT,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> int:
    """One pass over every online agent: one ListContainers call each.

    Agents are reconciled ``concurrency`` at a time so the pass stays short with
    many hosts, and each one is isolated: a BONNIE failure, a database failure
    or a timeout (covering both the BONNIE call and the database write) is
    logged and the pass continues with the others.
    """
    gate = asyncio.Semaphore(max(1, concurrency))

    async def fetch_and_apply(agent_id: str) -> int:
        client = registry.get(agent_id)
        if client is None:
            return 0
        containers = await client.list_containers()
        async with sessions() as session:
            service = EnvironmentService(session, registry, StreamSlots())
            return await service.reconcile_agent(uuid.UUID(agent_id), containers)

    async def one(agent_id: str, agent_name: str) -> int:
        async with gate:
            try:
                # wait_for rather than asyncio.timeout: the floor is Python 3.10
                return await asyncio.wait_for(
                    fetch_and_apply(agent_id), timeout=per_agent_timeout
                )
            except BonnieError as exc:
                _log.debug("reconcile skipped agent %s: %s", agent_name, exc)
            except asyncio.TimeoutError:
                _log.warning(
                    "reconcile skipped agent %s: BONNIE call or database write "
                    "exceeded %.0fs",
                    agent_name,
                    per_agent_timeout,
                )
            except Exception as exc:  # noqa: BLE001 - one agent must not abort the pass
                _log.error(
                    "reconcile failed for agent %s: %s", agent_name, exc, exc_info=exc
                )
            return 0

    online = [a for a in registry.agents() if a.status == STATUS_ONLINE]
    results = await asyncio.gather(*(one(a.id, a.name) for a in online))
    changed = sum(results)
    if changed:
        _log.info("reconciled environment status: changed=%d", changed)
    return changed


class Reconciler:
    """Runs :func:`reconcile_once` every ``interval`` seconds until stopped."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        registry: AgentRegistry,
        *,
        interval: float = DEFAULT_RECONCILE_INTERVAL,
        per_agent_timeout: float = DEFAULT_PER_AGENT_TIMEOUT,
        concurrency: int = DEFAULT_CONCURRENCY,
    ) -> None:
        self._sessions = sessions
        self._registry = registry
        self.interval = interval
        self.per_agent_timeout = per_agent_timeout
        self.concurrency = concurrency
        self._task: asyncio.Task[None] | None = None
        self.started_at: float | None = None
        self.last_success_at: float | None = None
        self.last_pass_seconds: float = 0.0

    def start(self) -> None:
        if self._task is None:
            self.started_at = time.monotonic()
            self._task = asyncio.create_task(self._loop(), name="karr-reconcile")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def seconds_since_success(self) -> float | None:
        """Age of the last completed pass, or of the start when none completed yet."""
        anchor = (
            self.last_success_at
            if self.last_success_at is not None
            else self.started_at
        )
        return None if anchor is None else time.monotonic() - anchor

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.interval)
            started = time.monotonic()
            try:
                await reconcile_once(
                    self._sessions,
                    self._registry,
                    per_agent_timeout=self.per_agent_timeout,
                    concurrency=self.concurrency,
                )
            except Exception as exc:  # noqa: BLE001 - the loop must survive
                _log.error("reconcile pass failed: %s", exc, exc_info=exc)
            else:
                self.last_success_at = time.monotonic()
                self.last_pass_seconds = self.last_success_at - started


class ReconcilerChecker:
    """Non-critical health check: the loop must complete a pass regularly."""

    name = "reconciler"

    def __init__(self, reconciler: Reconciler) -> None:
        self._r = reconciler

    async def check(self) -> None:
        r = self._r
        if r.started_at is None:
            raise RuntimeError("reconciler not started")
        age = r.seconds_since_success()
        # a pass may legitimately take longer than the interval with many
        # slow agents, so the budget grows with the last observed pass
        limit = r.interval * MISSED_PASSES_BEFORE_UNHEALTHY + max(
            r.per_agent_timeout, r.last_pass_seconds
        )
        if age is not None and age > limit:
            raise RuntimeError(
                f"no completed reconcile pass for {age:.0f}s (limit {limit:.0f}s)"
            )
