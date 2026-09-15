"""RegistryStore over the karr_agents table (feeds flag_commons' AgentRegistry)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from flag_commons.bonnie import Agent as RegistryAgent
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from karr.db.models import Agent
from karr.security import TokenCipher

_log = logging.getLogger(__name__)


class KarrRegistryStore:
    """Lists agents (with decrypted tokens) and persists poll results."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], cipher: TokenCipher
    ) -> None:
        self._sessions = session_factory
        self._cipher = cipher

    async def list(self) -> list[RegistryAgent]:
        async with self._sessions() as session:
            rows = (
                (await session.execute(select(Agent).order_by(Agent.name)))
                .scalars()
                .all()
            )
        agents: list[RegistryAgent] = []
        for row in rows:
            try:
                decrypted = self._cipher.decrypt(row.token_encrypted)
            except ValueError as exc:
                # Never poll or operate with a missing token: leave the agent out
                # of the registry so it shows as unreachable instead of silently
                # downgrading to unauthenticated calls.
                _log.error(
                    "agent %s token cannot be decrypted with KARR_SECRET_KEY; skipping: %s",
                    row.name,
                    exc,
                )
                continue
            agents.append(
                RegistryAgent(
                    id=str(row.id),
                    name=row.name,
                    url=row.url,
                    token=decrypted,
                    status=row.status,
                    last_seen_at=row.last_seen_at,
                    last_checked_at=row.last_checked_at,
                )
            )
        return agents

    async def update_status(
        self,
        agent_id: str,
        status: str,
        last_seen_at: datetime | None,
        last_checked_at: datetime,
    ) -> None:
        async with self._sessions() as session:
            await session.execute(
                update(Agent)
                .where(Agent.id == uuid.UUID(agent_id))
                .values(
                    status=status,
                    last_seen_at=last_seen_at,
                    last_checked_at=last_checked_at,
                )
            )
            await session.commit()
