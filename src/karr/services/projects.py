"""Project rules (plan §5.5): a project is a label on environments."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from karr.api.errors import ApiError
from karr.api.schemas import ProjectCreate, ProjectUpdate
from karr.db.models import Project
from karr.services.common import is_unique_violation


class ProjectService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list(self) -> list[Project]:
        return list(
            (await self._s.execute(select(Project).order_by(Project.name)))
            .scalars()
            .all()
        )

    async def get(self, project_id: uuid.UUID) -> Project:
        project = await self._s.get(Project, project_id)
        if project is None:
            raise ApiError(404, "project not found")
        return project

    async def create(self, body: ProjectCreate) -> Project:
        name = body.name.strip()
        if not name:
            raise ApiError(422, "name is required")
        project = Project(name=name, description=body.description.strip())
        self._s.add(project)
        try:
            await self._s.commit()
        except IntegrityError as exc:
            await self._s.rollback()
            if is_unique_violation(exc):
                raise ApiError(409, "project name already exists") from exc
            raise
        await self._s.refresh(project)
        return project

    async def update(self, project_id: uuid.UUID, body: ProjectUpdate) -> Project:
        project = await self.get(project_id)
        fields = body.model_dump(exclude_unset=True)
        if "name" in fields:
            name = (fields["name"] or "").strip()
            if not name:
                raise ApiError(422, "name is required")
            project.name = name
        if "description" in fields:
            project.description = (fields["description"] or "").strip()
        try:
            await self._s.commit()
        except IntegrityError as exc:
            await self._s.rollback()
            if is_unique_violation(exc):
                raise ApiError(409, "project name already exists") from exc
            raise
        await self._s.refresh(project)
        return project

    async def delete(self, project_id: uuid.UUID) -> None:
        project = await self.get(project_id)  # 404 if missing (K-D5)
        await self._s.delete(project)  # environments get project_id = NULL via the FK
        await self._s.commit()
