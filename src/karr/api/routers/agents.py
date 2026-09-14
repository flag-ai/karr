"""``/api/v1/agents`` (routes 9–13). Registration routes are mounted first.

The output models reproduce the Go ``omitempty`` (a null ``last_seen_at`` is
omitted); the status route omits the BONNIE sections that could not be
fetched.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from karr.api.schemas import AgentCreate, AgentOut, AgentStatusOut
from karr.db.session import get_session
from karr.security import require_admin
from karr.services.agents import AgentService
from karr.services.common import cipher_of, parse_uuid, registry_of

router = APIRouter(
    prefix="/api/v1/agents", tags=["agents"], dependencies=[Depends(require_admin)]
)
Session = Annotated[AsyncSession, Depends(get_session)]


def _service(request: Request, session: AsyncSession) -> AgentService:
    return AgentService(session, registry_of(request), cipher_of(request))


@router.get("", response_model=list[AgentOut])
async def list_agents(request: Request, session: Session) -> list[AgentOut]:
    return [AgentOut.model_validate(a) for a in await _service(request, session).list()]


@router.post("", response_model=AgentOut, status_code=201)
async def create_agent(
    body: AgentCreate, request: Request, session: Session
) -> AgentOut:
    return AgentOut.model_validate(await _service(request, session).create(body))


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(agent_id: str, request: Request, session: Session) -> AgentOut:
    return AgentOut.model_validate(
        await _service(request, session).get(parse_uuid(agent_id, "agent"))
    )


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: str,
    request: Request,
    session: Session,
    force: Annotated[bool, Query()] = False,
) -> Response:
    await _service(request, session).delete(parse_uuid(agent_id, "agent"), force=force)
    return Response(status_code=204)


@router.get("/{agent_id}/status", response_model=AgentStatusOut)
async def agent_status(
    agent_id: str, request: Request, session: Session
) -> JSONResponse:
    status = await _service(request, session).status(parse_uuid(agent_id, "agent"))
    return JSONResponse(status.to_wire())  # keeps nested nulls (gpus: null) like Go
