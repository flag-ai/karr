"""Default-agent seeding from KARR_DEFAULT_AGENT_URL (plan §5.2 step 7)."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from karr.db.models import Agent
from karr.security import TokenCipher

DEFAULT_AGENT_NAME = "default"

_log = logging.getLogger(__name__)


async def ensure_default_agent(
    sessions: async_sessionmaker[AsyncSession],
    cipher: TokenCipher,
    url: str,
    token: str,
) -> bool:
    """Insert an agent named ``default`` unless one with ``url`` exists. Returns True if inserted."""
    url = url.strip()
    if not url:
        return False
    async with sessions() as session:
        existing = (
            await session.execute(select(Agent).where(Agent.url == url))
        ).scalar_one_or_none()
        if existing is not None:
            return False
        session.add(
            Agent(
                name=DEFAULT_AGENT_NAME,
                url=url,
                token_encrypted=cipher.encrypt(token),
                status="offline",
            )
        )
        await session.commit()
    _log.info("registered default BONNIE agent: url=%s", url)
    return True
