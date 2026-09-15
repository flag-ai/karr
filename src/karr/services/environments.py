"""Environment rules (plan §5.5, K-D2/K-D3/K-D4/K-D5/K-D22)."""

from __future__ import annotations

import builtins
import logging
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from flag_commons.bonnie import (
    AgentRegistry,
    BonnieClient,
    BonnieError,
    BonnieNotFound,
    ContainerInfo,
    CreateContainerRequest,
)
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from karr.api.errors import ApiError
from karr.api.schemas import EnvironmentCreate
from karr.api.sse import StreamSlots, TooManyStreams
from karr.db.models import Agent, Environment, Project
from karr.services.common import is_foreign_key_violation, is_unique_violation

_log = logging.getLogger(__name__)

# state machine (K-D3): creating -> stopped after a successful create; stopped <-> running
TRANSITIONS: dict[str, dict[str, str]] = {
    "start": {"stopped": "running"},
    "stop": {"running": "stopped"},
}

# A row is ``creating`` for at most one BONNIE request (30 s client timeout).
# Older ``creating`` rows are the leftovers of a crash mid-create: the reconciler
# adopts their container by name or marks them ``error``, and they may be
# deleted. Younger ones are in flight and must be left alone, or a reconcile pass
# could bind a foreign container that merely shares the name.
CREATE_GRACE = timedelta(seconds=60)
CREATE_NEVER_COMPLETED = "create never completed"
CONTAINER_MISSING = "container missing"


def _age(env: Environment) -> timedelta:
    return datetime.now(timezone.utc) - env.created_at


@dataclass
class LogLease:
    """An upstream log iterator plus the slot release the relay must call."""

    lines: AsyncIterator[str]
    release: Callable[[], None]


class EnvironmentService:
    def __init__(
        self, session: AsyncSession, registry: AgentRegistry, slots: StreamSlots
    ) -> None:
        self._s = session
        self._registry = registry
        self._slots = slots

    async def list(self) -> builtins.list[Environment]:
        result = await self._s.execute(
            select(Environment).order_by(Environment.created_at.desc())
        )
        return list(result.scalars().all())

    async def get(self, env_id: uuid.UUID) -> Environment:
        env = await self._s.get(Environment, env_id)
        if env is None:
            raise ApiError(404, "environment not found")
        return env

    async def create(self, body: EnvironmentCreate) -> Environment:
        name = body.name.strip()
        image = body.image.strip()
        if not name:
            raise ApiError(422, "name is required")
        if not image:
            raise ApiError(422, "image is required")
        if await self._s.get(Agent, body.agent_id) is None:
            raise ApiError(400, "agent not found")  # K-D5 (Go: FK violation 500)
        if body.project_id is not None and (
            await self._s.get(Project, body.project_id) is None
        ):
            raise ApiError(400, "project not found")  # K-D5

        env = Environment(
            agent_id=body.agent_id,
            project_id=body.project_id,
            name=name,
            image=image,
            gpu=body.gpu,
            env=list(body.env),
            mounts=list(body.mounts),
            command=list(body.command),
            status="creating",
        )
        self._s.add(env)
        try:
            await self._s.commit()
        except IntegrityError as exc:
            await self._s.rollback()
            if is_unique_violation(exc):
                raise ApiError(
                    409, "an environment with that name already exists on this agent"
                ) from exc  # K-D22
            if is_foreign_key_violation(exc):  # agent/project deleted meanwhile
                raise ApiError(400, "agent or project not found") from exc
            raise
        await self._s.refresh(env)

        client = self._registry.get(str(body.agent_id))
        if client is None:
            await self._set_status(
                env.id, "error", "no BONNIE client registered for agent"
            )
            raise ApiError(502, "no BONNIE client registered for agent")
        try:
            container_id = await client.create_container(
                CreateContainerRequest(
                    name=name,
                    image=image,
                    env=env.env,
                    mounts=env.mounts,
                    gpu=env.gpu,
                    command=env.command,
                )
            )
        except BonnieError as exc:
            message = f"create container on agent failed: {exc.message}"
            await self._set_status(env.id, "error", message)
            raise ApiError(502, message) from exc
        await self._s.execute(
            update(Environment)
            .where(Environment.id == env.id)
            .values(container_id=container_id, status="stopped", status_message="")
        )
        await self._s.commit()
        await self._s.refresh(env)
        _log.info(
            "environment created: id=%s name=%s container_id=%s",
            env.id,
            env.name,
            container_id,
        )
        return env

    async def start(self, env_id: uuid.UUID) -> None:
        await self._transition(env_id, "start")

    async def stop(self, env_id: uuid.UUID) -> None:
        await self._transition(env_id, "stop")

    async def _transition(self, env_id: uuid.UUID, action: str) -> None:
        env = await self.get(env_id)
        target = TRANSITIONS[action].get(env.status)
        if target is None:
            raise ApiError(
                409, f"cannot {action} an environment that is {env.status}"
            )  # K-D3
        client = self._client_for(env)
        try:
            if action == "start":
                await client.start_container(env.container_id)
            else:
                await client.stop_container(env.container_id)
        except BonnieError as exc:
            message = f"{action} container failed: {exc.message}"
            await self._set_status(env.id, "error", message)
            raise ApiError(502, message) from exc
        await self._set_status(env.id, target, "")
        _log.info(
            "environment %s: id=%s",
            "started" if action == "start" else "stopped",
            env.id,
        )

    async def remove(self, env_id: uuid.UUID) -> None:
        env = await self.get(env_id)
        if env.status == "creating" and _age(env) < CREATE_GRACE:
            # the create is still in flight; deleting the row now would orphan
            # the container BONNIE is about to hand back
            raise ApiError(409, "environment is still being created")
        if env.container_id:
            client = self._client_for(env)
            try:
                await client.remove_container(env.container_id)
            except BonnieNotFound:
                pass  # already gone counts as success
            except BonnieError as exc:
                if env.status_message != CONTAINER_MISSING:
                    message = f"remove container failed: {exc.message}"
                    await self._set_status(env.id, "error", message)
                    raise ApiError(502, message) from exc
                # BONNIE answers 500, not 404, for a container that no longer
                # exists; the reconciler already established it is gone
                _log.info(
                    "environment %s: container %s already missing, dropping row",
                    env.id,
                    env.container_id,
                )
        await self._s.delete(env)
        await self._s.commit()
        _log.info("environment removed: id=%s", env_id)

    async def log_lines(self, env_id: uuid.UUID, client_id: str = "") -> LogLease:
        """Resolve the row, its container, its agent and a stream slot before the SSE headers go out.

        BONNIE itself is not contacted until the relay pulls the first line, so a
        container that vanished after the last reconcile pass surfaces as an
        ``event: error`` frame rather than a status code (K-D2).
        """
        env = await self.get(env_id)
        if not env.container_id:
            raise ApiError(409, "environment has no container")
        client = self._client_for(env)
        try:
            release = self._slots.acquire(str(env.agent_id), client_id)
        except TooManyStreams as exc:
            raise ApiError(429, f"{exc}; close another log view first") from exc
        return LogLease(client.stream_container_logs(env.container_id), release)

    async def reconcile_agent(
        self, agent_id: uuid.UUID, containers: builtins.list[ContainerInfo]
    ) -> int:
        """K-D3: map BONNIE's container states onto the environments of one agent.

        A row left ``creating`` by a crash between BONNIE's create and our
        commit is adopted through its container name (unique per agent) once it
        is older than :data:`CREATE_GRACE`; if no container exists by then it
        becomes ``error`` so the operator can delete it.
        """
        by_id = {c.id: c for c in containers}
        by_name = {c.name: c for c in containers}
        rows = (
            (
                await self._s.execute(
                    select(Environment).where(Environment.agent_id == agent_id)
                )
            )
            .scalars()
            .all()
        )
        changed = 0
        for env in rows:
            if env.status == "creating":
                if _age(env) < CREATE_GRACE:
                    continue  # in flight: create() will finish or fail it
                container = by_name.get(env.name)
                if container is None:
                    env.status, env.status_message = "error", CREATE_NEVER_COMPLETED
                else:
                    env.container_id = container.id
                    env.status, env.status_message = _observed(container)
                changed += 1
                continue
            if not env.container_id:
                continue  # an error row without a container has nothing to reconcile
            container = by_id.get(env.container_id)
            status, message = _observed(container)
            if env.status != status or env.status_message != message:
                env.status, env.status_message = status, message
                changed += 1
        if changed:
            await self._s.commit()
        return changed

    def _client_for(self, env: Environment) -> BonnieClient:
        client = self._registry.get(str(env.agent_id))
        if client is None:
            raise ApiError(502, "no BONNIE client registered for agent")
        return client

    async def _set_status(self, env_id: uuid.UUID, status: str, message: str) -> None:
        await self._s.execute(
            update(Environment)
            .where(Environment.id == env_id)
            .values(status=status, status_message=message)
        )
        await self._s.commit()


def _observed(container: ContainerInfo | None) -> tuple[str, str]:
    if container is None:
        return "error", CONTAINER_MISSING
    if container.state == "running":
        return "running", ""
    return "stopped", ""
