"""Agent rules (plan §5.5, K-D4, K-D12, K-D13)."""

from __future__ import annotations

import logging
import uuid

from flag_commons.bonnie import Agent as RegistryAgent
from flag_commons.bonnie import AgentRegistry, BonnieError, BonnieNotFound
from sqlalchemy import select
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

    async def list(self) -> list[Agent]:
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
        """K-D4: 409 while environments exist; ``force`` removes their containers first."""
        agent = await self.get(agent_id)
        envs = list(
            (
                await self._s.execute(
                    select(Environment).where(Environment.agent_id == agent_id)
                )
            )
            .scalars()
            .all()
        )
        if envs and not force:
            raise ApiError(
                409,
                f"agent has {len(envs)} environment(s); delete them or pass force=true",
            )
        if envs:
            client = self._registry.get(str(agent_id))
            for env in envs:
                if env.container_id and client is not None:
                    try:
                        await client.remove_container(env.container_id)
                    except BonnieNotFound:
                        pass
                    except BonnieError as exc:  # best effort, logged
                        _log.warning(
                            "could not remove container during forced agent delete: env=%s error=%s",
                            env.id,
                            exc,
                        )
                await self._s.delete(env)
            await self._s.flush()  # environments first: the FK is RESTRICT
        await self._s.delete(agent)
        await self._s.commit()
        await self._registry.remove(str(agent_id))
        _log.info("agent deleted: id=%s name=%s", agent_id, agent.name)

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
