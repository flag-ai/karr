"""Background reconciliation of environment status against BONNIE (K-D3)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid

from flag_commons.bonnie import STATUS_ONLINE, AgentRegistry, BonnieError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from karr.services.environments import EnvironmentService

DEFAULT_RECONCILE_INTERVAL = 30.0

_log = logging.getLogger(__name__)


async def reconcile_once(
    sessions: async_sessionmaker[AsyncSession], registry: AgentRegistry
) -> int:
    """One pass over every online agent: one ListContainers call each."""
    changed = 0
    for agent in registry.agents():
        if agent.status != STATUS_ONLINE:
            continue
        client = registry.get(agent.id)
        if client is None:
            continue
        try:
            containers = await client.list_containers()
        except BonnieError as exc:
            _log.debug("reconcile skipped agent %s: %s", agent.name, exc)
            continue
        async with sessions() as session:
            changed += await EnvironmentService(session, registry).reconcile_agent(
                uuid.UUID(agent.id), containers
            )
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
    ) -> None:
        self._sessions = sessions
        self._registry = registry
        self.interval = interval
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="karr-reconcile")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.interval)
            try:
                await reconcile_once(self._sessions, self._registry)
            except Exception as exc:  # noqa: BLE001 - the loop must survive
                _log.error("reconcile pass failed: %s", exc)
