"""Agent provisioning and self-registration (plan §5.5, K-D6/7/8/23)."""

from __future__ import annotations

import builtins
import logging
import uuid
from datetime import datetime, timedelta, timezone

from flag_commons.bonnie import Agent as RegistryAgent
from flag_commons.bonnie import AgentRegistry
from flag_commons.install import InstallScriptError, RegistrationFailed, install_command
from flag_commons.install.fastapi import TokenLookupError
from flag_commons.install.render import SAFE_ADDRESS
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from karr.api.errors import ApiError
from karr.db.models import Agent, AgentRegistration
from karr.security import (
    TokenCipher,
    generate_registration_token,
    hash_registration_token,
)
from karr.services.common import is_unique_violation, validate_agent_url

_log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ProvisionResult:
    def __init__(
        self, registration: AgentRegistration, token: str, command: str
    ) -> None:
        self.id = registration.id
        self.token = token
        self.install_command = command
        self.expires_at = registration.expires_at


class RegistrationService:
    def __init__(
        self,
        session: AsyncSession,
        registry: AgentRegistry,
        cipher: TokenCipher,
        *,
        ttl_seconds: int,
        allow_insecure: bool = False,
    ) -> None:
        self._s = session
        self._registry = registry
        self._cipher = cipher
        self._ttl = ttl_seconds
        self._allow_insecure = allow_insecure

    async def provision(self, label: str, server_url: str) -> ProvisionResult:
        """Create a pending registration; the plaintext token is returned once."""
        label = label.strip()
        if not label:
            raise ApiError(422, "label is required")
        await self.expire_stale()
        token = generate_registration_token()
        # Render first: a misconfigured server URL must not leave a usable token behind.
        try:
            command = install_command(
                server_url, token, allow_insecure=self._allow_insecure
            )
        except InstallScriptError as exc:
            raise ApiError(
                503, f"install command cannot be built: {exc}; set KARR_PUBLIC_URL"
            ) from exc
        registration = AgentRegistration(
            token_hash=hash_registration_token(token),
            label=label,
            status="pending",
            expires_at=func.now() + timedelta(seconds=self._ttl),  # DB clock, like Go
        )
        self._s.add(registration)
        await self._s.commit()
        await self._s.refresh(registration)
        _log.info(
            "provisioned agent registration: id=%s label=%s", registration.id, label
        )
        return ProvisionResult(registration, token, command)

    async def list(self) -> builtins.list[AgentRegistration]:
        await self.expire_stale()
        result = await self._s.execute(
            select(AgentRegistration).order_by(AgentRegistration.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete(self, registration_id: uuid.UUID) -> None:
        registration = await self._s.get(AgentRegistration, registration_id)
        if registration is None:
            raise ApiError(404, "registration not found")  # K-D5 (Go: 204)
        await self._s.delete(registration)
        await self._s.commit()

    async def expire_stale(self) -> None:
        """Flip pending rows past their expiry to ``expired`` (K-D8, computed on read)."""
        await self._s.execute(
            update(AgentRegistration)
            .where(
                AgentRegistration.status == "pending",
                AgentRegistration.expires_at <= _now(),
            )
            .values(status="expired")
        )
        await self._s.commit()

    async def lookup_for_install(self, token: str) -> AgentRegistration:
        """K-D7: the install script is served only for a pending, unexpired token."""
        registration = (
            await self._s.execute(
                select(AgentRegistration).where(
                    AgentRegistration.token_hash == hash_registration_token(token)
                )
            )
        ).scalar_one_or_none()
        if registration is None:
            raise TokenLookupError(404, "registration not found")
        if registration.status != "pending" or registration.expires_at <= _now():
            raise TokenLookupError(410, "registration is claimed or expired")
        return registration

    async def register(
        self,
        token: str,
        source_ip: str,
        port: int,
        auth_token: str,
        address: str | None,
    ) -> Agent:
        """Claim the token and create the agent in one transaction (K-D6)."""
        claimed = (
            await self._s.execute(
                update(AgentRegistration)
                .where(
                    AgentRegistration.token_hash == hash_registration_token(token),
                    AgentRegistration.status == "pending",
                    AgentRegistration.expires_at > _now(),
                )
                .values(status="claimed", claimed_at=_now())
                .returning(AgentRegistration.id, AgentRegistration.label)
            )
        ).first()
        if claimed is None:
            await self._s.rollback()
            raise RegistrationFailed("invalid or expired registration token")
        registration_id, label = claimed
        host = (address or "").strip() or source_ip
        if not SAFE_ADDRESS.fullmatch(host):
            await self._s.rollback()
            raise RegistrationFailed("address must be a bare hostname or IP address")
        try:
            url = validate_agent_url(f"http://{host}:{port}")  # K-D13 applies here too
        except ApiError as exc:
            await self._s.rollback()
            raise RegistrationFailed(exc.message) from exc
        agent = Agent(
            name=label or host,
            url=url,
            token_encrypted=self._cipher.encrypt(auth_token),
            status="offline",
        )
        self._s.add(agent)
        try:
            await self._s.flush()
            await self._s.execute(
                update(AgentRegistration)
                .where(AgentRegistration.id == registration_id)
                .values(agent_id=agent.id)
            )
            await self._s.commit()
        except IntegrityError as exc:
            await self._s.rollback()  # the claim rolls back too: the token stays usable
            if is_unique_violation(exc):
                raise RegistrationFailed(
                    f"an agent named {agent.name!r} already exists"
                ) from exc
            raise
        await self._s.refresh(agent)
        await self._registry.upsert(
            RegistryAgent(
                id=str(agent.id),
                name=agent.name,
                url=agent.url,
                token=auth_token,
                status="offline",
            )
        )
        _log.info(
            "agent registered via install script: id=%s name=%s url=%s",
            agent.id,
            agent.name,
            agent.url,
        )
        return agent
