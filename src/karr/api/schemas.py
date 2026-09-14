"""Request and response models with the Go JSON shapes (plan §5.4)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from flag_commons.bonnie import GPUSnapshot, SystemInfoResponse
from pydantic import BaseModel, ConfigDict, Field, field_serializer


def rfc3339(value: datetime | None) -> str | None:
    """Go's encoding/json format: UTC with a trailing ``Z``."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    text = value.astimezone(timezone.utc).isoformat()
    return text.replace("+00:00", "Z")


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at", "updated_at", check_fields=False)
    def _ser_required_ts(self, value: datetime) -> str:
        return rfc3339(value) or ""


class _In(BaseModel):
    """Request bodies reject unknown fields (K-D21)."""

    model_config = ConfigDict(extra="forbid")


# --- agents -------------------------------------------------------------------


class AgentOut(_Out):
    """The token is never serialized (it is not even a field here)."""

    id: uuid.UUID
    name: str
    url: str
    status: str
    last_seen_at: datetime | None = None
    last_checked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @field_serializer("last_seen_at", "last_checked_at")
    def _ser_optional_ts(self, value: datetime | None) -> str | None:
        return rfc3339(value)


class AgentCreate(_In):
    name: str
    url: str
    token: str = ""


class AgentStatusOut(BaseModel):
    """``system`` and ``gpu`` are omitted when BONNIE could not be reached."""

    model_config = ConfigDict(extra="ignore")

    agent: AgentOut
    system: SystemInfoResponse | None = None
    gpu: GPUSnapshot | None = None

    def to_wire(self) -> dict[str, Any]:
        data: dict[str, Any] = {"agent": self.agent.model_dump(mode="json")}
        if self.system is not None:
            data["system"] = self.system.model_dump(mode="json")
        if self.gpu is not None:
            data["gpu"] = self.gpu.model_dump(mode="json")
        return data


# --- projects -----------------------------------------------------------------


class ProjectOut(_Out):
    id: uuid.UUID
    name: str
    description: str = ""
    created_at: datetime
    updated_at: datetime


class ProjectCreate(_In):
    name: str
    description: str = ""


class ProjectUpdate(_In):
    """Absent fields stay unchanged; present ones are trimmed and applied."""

    name: str | None = None
    description: str | None = None


# --- environments -------------------------------------------------------------


class EnvironmentOut(_Out):
    id: uuid.UUID
    project_id: uuid.UUID | None = None
    agent_id: uuid.UUID
    name: str
    image: str
    container_id: str = ""
    status: str
    status_message: str = ""
    gpu: bool
    env: list[str] = Field(default_factory=list)
    mounts: list[str] = Field(default_factory=list)
    command: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class EnvironmentCreate(_In):
    agent_id: uuid.UUID
    project_id: uuid.UUID | None = None
    name: str
    image: str
    gpu: bool = False
    env: list[str] = Field(default_factory=list)
    mounts: list[str] = Field(default_factory=list)
    command: list[str] = Field(default_factory=list)
