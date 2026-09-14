"""Agent rules (plan §5.5, K-D4, K-D12, K-D13)."""

from __future__ import annotations

import builtins
import logging
import uuid
from collections.abc import Sequence

from flag_commons.bonnie import Agent as RegistryAgent
from flag_commons.bonnie import AgentRegistry, BonnieError, BonnieNotFound
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from karr.api.errors import ApiError
from karr.api.schemas import AgentCreate, AgentOut, AgentStatusOut
from karr.db.models import Agent, Environment
from karr.security import TokenCipher
from karr.services.common import is_unique_violation, validate_agent_url

_log = logging.getLogger(__name__)


class AgentService:
    def __init__(
        self, session: AsyncSession, registry: AgentRegistry, cipher: TokenCipher
    ) -> None:
        self._s = session
        self._registry = registry
        self._cipher = cipher

    async def list(self) -> builtins.list[Agent]:  # noqa: A003 - the Go service API
        return list(
            (await self._s.execute(select(Agent).order_by(Agent.name))).scalars().all()
        )

    async def get(self, agent_id: uuid.UUID) -> Agent:
        agent = await self._s.get(Agent, agent_id)
        if agent is None:
            raise ApiError(404, "agent not found")
        return agent

    async def create(self, body: AgentCreate) -> Agent:
        name = body.name.strip()
        if not name:
            raise ApiError(422, "name is required")
        url = validate_agent_url(body.url)
        agent = Agent(
            name=name,
            url=url,
            token_encrypted=self._cipher.encrypt(body.token),
            status="offline",
        )
        self._s.add(agent)
        try:
            await self._s.commit()
        except IntegrityError as exc:
            await self._s.rollback()
            if is_unique_violation(exc):
                raise ApiError(409, "agent name already exists") from exc
            raise
        await self._s.refresh(agent)
        await self._registry.upsert(self._registry_agent(agent, body.token))
        _log.info("agent registered: id=%s name=%s", agent.id, agent.name)
        return agent

    async def delete(self, agent_id: uuid.UUID, *, force: bool = False) -> None:
        """K-D4: 409 while environments exist; ``force`` removes their containers first.

        Container removal happens before the delete transaction. If any
        container cannot be removed the rows are kept and the call answers 409
        naming them, so an operator is never told a workload is gone while it
        is still running.
        """
        agent = await self.get(agent_id)
        agent_name = agent.name
        rows = (
            await self._s.execute(
                select(Environment.name, Environment.container_id).where(
                    Environment.agent_id == agent_id
                )
            )
        ).all()
        envs = [(name, container_id) for name, container_id in rows]
        if envs and not force:
            raise ApiError(
                409,
                f"agent has {len(envs)} environment(s); delete them or pass force=true",
            )
        await (
            self._s.rollback()
        )  # release the read transaction before talking to BONNIE

        if envs:
            failed = await self._remove_containers(agent_id, agent_name, envs)
            if failed:
                raise ApiError(
                    409,
                    "could not remove container(s) on the agent: " + ", ".join(failed),
                )
            await self._s.execute(
                delete(Environment).where(Environment.agent_id == agent_id)
            )
        await self._s.execute(delete(Agent).where(Agent.id == agent_id))
        try:
            await self._s.commit()
        except IntegrityError as exc:
            await self._s.rollback()
            raise ApiError(
                409, "agent gained environments while being deleted; retry"
            ) from exc
        await self._registry.remove(str(agent_id))
        _log.info("agent deleted: id=%s name=%s", agent_id, agent_name)

    async def _remove_containers(
        self, agent_id: uuid.UUID, agent_name: str, envs: Sequence[tuple[str, str]]
    ) -> builtins.list[str]:
        client = self._registry.get(str(agent_id))
        with_containers = [(name, cid) for name, cid in envs if cid]
        if not with_containers:
            return []
        if client is None:
            _log.warning(
                "no BONNIE client registered for agent %s; cannot remove %d container(s)",
                agent_name,
                len(with_containers),
            )
            return [name for name, _ in with_containers]
        failed: builtins.list[str] = []
        for name, container_id in with_containers:
            try:
                await client.remove_container(container_id)
            except BonnieNotFound:
                continue  # already gone counts as removed
            except BonnieError as exc:
                _log.warning("could not remove container: env=%s error=%s", name, exc)
                failed.append(name)
        return failed

    async def status(self, agent_id: uuid.UUID) -> AgentStatusOut:
        """Live system and GPU info; BONNIE failures are omitted, the call still succeeds."""
        agent = await self.get(agent_id)
        out = AgentStatusOut(agent=AgentOut.model_validate(agent))
        client = self._registry.get(str(agent_id))
        if client is None:
            _log.warning("no BONNIE client registered for agent: id=%s", agent_id)
            return out
        try:
            out.system = await client.system_info()
        except BonnieError as exc:
            _log.error(
                "failed to get system info from agent: id=%s error=%s", agent_id, exc
            )
        try:
            out.gpu = await client.gpu_status()
        except BonnieError as exc:
            _log.error(
                "failed to get GPU status from agent: id=%s error=%s", agent_id, exc
            )
        return out

    @staticmethod
    def _registry_agent(agent: Agent, token: str) -> RegistryAgent:
        return RegistryAgent(
            id=str(agent.id),
            name=agent.name,
            url=agent.url,
            token=token,
            status=agent.status,
            last_seen_at=agent.last_seen_at,
            last_checked_at=agent.last_checked_at,
        )
