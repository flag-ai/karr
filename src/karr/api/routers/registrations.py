"""Provisioning (routes 6–8) plus the install script and self-registration (4–5).

Mounted before ``/api/v1/agents/{id}`` so the static paths win.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Request, Response
from flag_commons.install import (
    InstallScriptError,
    RegisterRequest,
    RegisterResult,
    validate_token,
)
from flag_commons.install.fastapi import (
    TokenLookupError,
    install_router,
)
from sqlalchemy.ext.asyncio import AsyncSession

from karr.api.errors import ApiError
from karr.api.ratelimit import rate_limited
from karr.api.schemas import ProvisionOut, ProvisionRequest, RegistrationOut
from karr.config import KarrConfig
from karr.db.session import get_session
from karr.security import require_admin
from karr.services.common import cipher_of, parse_uuid, registry_of
from karr.services.registrations import RegistrationService

PROVISION_LIMIT = (
    "provision_limiter",
    30,
    0.5,
)  # (app.state attribute, capacity, refill/s)
REGISTER_LIMIT = ("register_limiter", 30, 0.5)

Session = Annotated[AsyncSession, Depends(get_session)]


def _service(request: Request, session: AsyncSession) -> RegistrationService:
    cfg: KarrConfig = request.app.state.config
    return RegistrationService(
        session,
        registry_of(request),
        cipher_of(request),
        ttl_seconds=cfg.registration_ttl,
        allow_insecure=cfg.allow_insecure_install,
    )


def server_url_for(request: Request) -> str:
    """The control-plane URL embedded in install scripts and one-liners.

    Only ``KARR_PUBLIC_URL`` is used. Neither the request's ``Host`` header nor
    a proxy's ``X-Forwarded-Host`` is trusted for this: a forged value would
    point ``curl | sudo bash`` at an attacker's server, and behind a proxy
    that sets ``X-Forwarded-For`` the peer address is rewritten anyway.
    """
    cfg: KarrConfig = request.app.state.config
    if cfg.public_url:
        return cfg.public_url
    raise ApiError(
        503, "KARR_PUBLIC_URL is not configured; it is required for provisioning"
    )


admin_router = APIRouter(
    prefix="/api/v1/agents",
    tags=["registrations"],
    dependencies=[Depends(require_admin)],
)


@admin_router.post(
    "/provision",
    response_model=ProvisionOut,
    status_code=201,
    dependencies=[Depends(rate_limited(PROVISION_LIMIT[0]))],
)
async def provision(
    body: ProvisionRequest, request: Request, session: Session
) -> ProvisionOut:
    result = await _service(request, session).provision(
        body.label, server_url_for(request)
    )
    return ProvisionOut(
        id=result.id,
        token=result.token,
        install_command=result.install_command,
        expires_at=result.expires_at,
    )


@admin_router.get("/registrations", response_model=list[RegistrationOut])
async def list_registrations(
    request: Request, session: Session
) -> list[RegistrationOut]:
    return [
        RegistrationOut.model_validate(r)
        for r in await _service(request, session).list()
    ]


@admin_router.delete("/registrations/{registration_id}", status_code=204)
async def delete_registration(
    registration_id: str, request: Request, session: Session
) -> Response:
    await _service(request, session).delete(parse_uuid(registration_id, "registration"))
    return Response(status_code=204)


def public_router(app: FastAPI) -> APIRouter:
    """``GET /install.sh`` and ``POST /agents/register`` (registration-token auth).

    Include it with ``prefix="/api/v1"``. The callbacks open their own database
    session from the app state, since flag-commons calls them without a request.
    """
    config: KarrConfig = app.state.config

    def _service_for(session: AsyncSession) -> RegistrationService:
        return RegistrationService(
            session,
            app.state.registry,
            app.state.cipher,
            ttl_seconds=config.registration_ttl,
            allow_insecure=config.allow_insecure_install,
        )

    async def token_lookup(request: Request) -> str:
        token = request.query_params.get("token", "")
        if not token:
            raise TokenLookupError(400, "missing token parameter")
        try:
            validate_token(token)
        except InstallScriptError as exc:
            raise TokenLookupError(400, str(exc)) from exc
        async with app.state.session_factory() as session:
            await _service_for(session).lookup_for_install(token)
        return token

    async def register(req: RegisterRequest, source_ip: str) -> RegisterResult:
        async with app.state.session_factory() as session:
            agent = await _service_for(session).register(
                req.registration_token, source_ip, req.port, req.auth_token, req.address
            )
        return RegisterResult(
            agent_id=str(agent.id), message="agent registered successfully"
        )

    return install_router(
        token_lookup=token_lookup,
        register=register,
        server_url=server_url_for,  # the same resolver as provision, never a header
        trusted_proxies=config.trusted_proxies,
        allow_insecure=config.allow_insecure_install,
    )
