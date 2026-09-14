"""``/api/v1/environments`` (routes 19–25)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from karr.api.schemas import EnvironmentCreate, EnvironmentOut
from karr.api.sse import relay, sse_response
from karr.db.session import get_session
from karr.security import require_admin
from karr.services.common import parse_uuid, registry_of
from karr.services.environments import EnvironmentService

router = APIRouter(
    prefix="/api/v1/environments",
    tags=["environments"],
    dependencies=[Depends(require_admin)],
)
Session = Annotated[AsyncSession, Depends(get_session)]


def _service(request: Request, session: AsyncSession) -> EnvironmentService:
    return EnvironmentService(session, registry_of(request))


@router.get("", response_model=list[EnvironmentOut])
async def list_environments(request: Request, session: Session) -> list[EnvironmentOut]:
    return [
        EnvironmentOut.model_validate(e)
        for e in await _service(request, session).list()
    ]


@router.post("", response_model=EnvironmentOut, status_code=201)
async def create_environment(
    body: EnvironmentCreate, request: Request, session: Session
) -> EnvironmentOut:
    return EnvironmentOut.model_validate(await _service(request, session).create(body))


@router.get("/{env_id}", response_model=EnvironmentOut)
async def get_environment(
    env_id: str, request: Request, session: Session
) -> EnvironmentOut:
    return EnvironmentOut.model_validate(
        await _service(request, session).get(parse_uuid(env_id, "environment"))
    )


@router.post("/{env_id}/start", status_code=204)
async def start_environment(
    env_id: str, request: Request, session: Session
) -> Response:
    await _service(request, session).start(parse_uuid(env_id, "environment"))
    return Response(status_code=204)


@router.post("/{env_id}/stop", status_code=204)
async def stop_environment(env_id: str, request: Request, session: Session) -> Response:
    await _service(request, session).stop(parse_uuid(env_id, "environment"))
    return Response(status_code=204)


@router.delete("/{env_id}", status_code=204)
async def remove_environment(
    env_id: str, request: Request, session: Session
) -> Response:
    await _service(request, session).remove(parse_uuid(env_id, "environment"))
    return Response(status_code=204)


@router.get("/{env_id}/logs", include_in_schema=True)
async def environment_logs(env_id: str, request: Request, session: Session) -> Response:
    """SSE relay of the container logs (K-D2): keepalives, `event: end`, `event: error`."""
    lines = await _service(request, session).log_lines(
        parse_uuid(env_id, "environment")
    )
    keepalive = getattr(request.app.state, "sse_keepalive_seconds", None)
    frames = relay(lines, keepalive_seconds=keepalive) if keepalive else relay(lines)
    return sse_response(frames)
