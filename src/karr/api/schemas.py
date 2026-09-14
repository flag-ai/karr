"""Request and response models with the Go JSON shapes (plan §5.4)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, ClassVar

from flag_commons.bonnie import GPUSnapshot, SystemInfoResponse
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    field_serializer,
    model_serializer,
)


def rfc3339(value: datetime | None) -> str | None:
    """RFC 3339 in UTC with a trailing ``Z``.

    Go emitted the same instant in the server's local offset with nanosecond
    precision trimmed of trailing zeros; the contract replay normalises
    timestamps, so only the instant has to match.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    text = value.astimezone(timezone.utc).isoformat()
    return text.replace("+00:00", "Z")


class _Out(BaseModel):
    """Response base with the Go ``omitempty`` rule.

    Keys listed in ``OMIT_EMPTY`` are dropped from the wire when their value is
    ``None``, ``""`` or an empty list, matching the Go struct tags.
    """

    model_config = ConfigDict(from_attributes=True)
    OMIT_EMPTY: ClassVar[frozenset[str]] = frozenset()

    @model_serializer(mode="wrap")
    def _omit_empty(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for key in self.OMIT_EMPTY:
            if key in data and data[key] in (None, "", []):
                del data[key]
        return data

    @field_serializer("created_at", "updated_at", check_fields=False)
    def _ser_required_ts(self, value: datetime) -> str:
        return rfc3339(value) or ""


class _In(BaseModel):
    """Request bodies reject unknown fields (K-D21)."""

    model_config = ConfigDict(extra="forbid")


# --- agents -------------------------------------------------------------------


class AgentOut(_Out):
    """The token is never serialized (it is not even a field here)."""

    OMIT_EMPTY = frozenset({"last_seen_at", "last_checked_at"})

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

    agent: AgentOut
    system: SystemInfoResponse | None = None
    gpu: GPUSnapshot | None = None

    def to_wire(self) -> dict[str, Any]:
        """Omit only the top-level sections; nested nulls (``gpus: null``) stay."""
        data: dict[str, Any] = {
            "agent": self.agent.model_dump(mode="json", exclude_defaults=True)
        }
        if self.system is not None:
            data["system"] = self.system.model_dump(mode="json")
        if self.gpu is not None:
            data["gpu"] = self.gpu.model_dump(mode="json")
        return data


# --- projects -----------------------------------------------------------------


class ProjectOut(_Out):
    OMIT_EMPTY = frozenset({"description"})

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
    OMIT_EMPTY = frozenset(
        {"project_id", "container_id", "status_message", "env", "mounts", "command"}
    )

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


# --- registrations ------------------------------------------------------------


class ProvisionRequest(_In):
    label: str = Field(max_length=200)


class ProvisionOut(BaseModel):
    """The plaintext token appears here exactly once."""

    id: uuid.UUID
    token: str
    install_command: str
    expires_at: datetime

    @field_serializer("expires_at")
    def _ser_expires(self, value: datetime) -> str:
        return rfc3339(value) or ""


class RegistrationOut(_Out):
    OMIT_EMPTY = frozenset({"agent_id", "claimed_at"})

    id: uuid.UUID
    label: str
    status: str
    agent_id: uuid.UUID | None = None
    created_at: datetime
    claimed_at: datetime | None = None
    expires_at: datetime

    @field_serializer("claimed_at", "expires_at")
    def _ser_ts(self, value: datetime | None) -> str | None:
        return rfc3339(value)
