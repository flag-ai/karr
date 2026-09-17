"""SQLAlchemy models for the four KARR tables (plan §5.6).

The columns mirror the Go migrations; the deliberate changes are marked
with their K-D ids: ``token_encrypted`` (K-D12), ``last_checked_at``
(K-D10), ``ON DELETE RESTRICT`` on ``karr_environments.agent_id`` (K-D4),
``UNIQUE (agent_id, name)`` (K-D22), ``status_message``, and CHECK
constraints on every status column.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

AGENT_STATUSES = ("online", "offline", "unauthorized")
ENVIRONMENT_STATUSES = ("creating", "running", "stopped", "error")
REGISTRATION_STATUSES = ("pending", "claimed", "expired")


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )


def _timestamp(
    *, nullable: bool = False, default_now: bool = True, onupdate: bool = False
) -> Mapped[Any]:
    kwargs: dict[str, Any] = {"nullable": nullable}
    if default_now:
        kwargs["server_default"] = text("now()")
    if onupdate:
        kwargs["onupdate"] = text("now()")
    return mapped_column(DateTime(timezone=True), **kwargs)


class Agent(Base):
    __tablename__ = "karr_agents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('online', 'offline', 'unauthorized')",
            name="ck_karr_agents_status",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    token_encrypted: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''")
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'offline'")
    )
    last_seen_at: Mapped[datetime | None] = _timestamp(nullable=True, default_now=False)
    last_checked_at: Mapped[datetime | None] = _timestamp(
        nullable=True, default_now=False
    )
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime] = _timestamp(onupdate=True)


class Project(Base):
    __tablename__ = "karr_projects"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''")
    )
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime] = _timestamp(onupdate=True)


class Environment(Base):
    __tablename__ = "karr_environments"
    __table_args__ = (
        UniqueConstraint("agent_id", "name", name="uq_karr_environments_agent_name"),
        CheckConstraint(
            "status IN ('creating', 'running', 'stopped', 'error')",
            name="ck_karr_environments_status",
        ),
        Index("idx_karr_environments_agent_id", "agent_id"),
        Index("idx_karr_environments_project_id", "project_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("karr_projects.id", ondelete="SET NULL"),
        nullable=True,
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("karr_agents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    image: Mapped[str] = mapped_column(Text, nullable=False)
    container_id: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''")
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'creating'")
    )
    status_message: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''")
    )
    gpu: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    env: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    mounts: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    command: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = _timestamp()
    updated_at: Mapped[datetime] = _timestamp(onupdate=True)


class AgentRegistration(Base):
    __tablename__ = "karr_agent_registrations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'claimed', 'expired')",
            name="ck_karr_agent_registrations_status",
        ),
        Index(
            "idx_registrations_pending_expires",
            "expires_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    label: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'")
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("karr_agents.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = _timestamp()
    claimed_at: Mapped[datetime | None] = _timestamp(nullable=True, default_now=False)
    expires_at: Mapped[datetime] = _timestamp(default_now=False)
