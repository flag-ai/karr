"""``/api/v1/projects`` (routes 14–18).

The output models reproduce the Go ``omitempty``: an empty description is
omitted from the wire, as it was.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from karr.api.schemas import ProjectCreate, ProjectOut, ProjectUpdate
from karr.db.session import get_session
from karr.security import require_admin
from karr.services.common import parse_uuid
from karr.services.projects import ProjectService

router = APIRouter(
    prefix="/api/v1/projects", tags=["projects"], dependencies=[Depends(require_admin)]
)
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=list[ProjectOut])
async def list_projects(session: Session) -> list[ProjectOut]:
    return [ProjectOut.model_validate(p) for p in await ProjectService(session).list()]


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectCreate, session: Session) -> ProjectOut:
    return ProjectOut.model_validate(await ProjectService(session).create(body))


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: str, session: Session) -> ProjectOut:
    return ProjectOut.model_validate(
        await ProjectService(session).get(parse_uuid(project_id, "project"))
    )


@router.put("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: str, body: ProjectUpdate, session: Session
) -> ProjectOut:
    return ProjectOut.model_validate(
        await ProjectService(session).update(parse_uuid(project_id, "project"), body)
    )


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str, session: Session) -> Response:
    await ProjectService(session).delete(parse_uuid(project_id, "project"))
    return Response(status_code=204)
