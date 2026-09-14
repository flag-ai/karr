"""Default-agent seeding from KARR_DEFAULT_AGENT_URL (plan §5.2 step 7)."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from karr.api.errors import ApiError
from karr.db.models import Agent
from karr.security import TokenCipher
from karr.services.common import validate_agent_url

DEFAULT_AGENT_NAME = "default"

_log = logging.getLogger(__name__)


async def ensure_default_agent(
    sessions: async_sessionmaker[AsyncSession],
    cipher: TokenCipher,
    url: str,
    token: str,
) -> bool:
    """Insert an agent named ``default`` unless one with ``url`` exists.

    The URL goes through the same validation as ``POST /api/v1/agents``;
    a bad value is logged and skipped. Returns True when a row was inserted.
    """
    if not url.strip():
        return False
    try:
        url = validate_agent_url(url)
    except ApiError as exc:
        _log.warning("KARR_DEFAULT_AGENT_URL rejected, not seeding: %s", exc.message)
        return False
    async with sessions() as session:
        existing = (
            await session.execute(select(Agent.id).where(Agent.url == url).limit(1))
        ).first()
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
