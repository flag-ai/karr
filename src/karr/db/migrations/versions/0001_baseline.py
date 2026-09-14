"""Baseline: the four KARR tables (fresh database, plan §5.6).

Revision ID: 0001
Revises:
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _ts(nullable: bool = False, default_now: bool = True) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        sa.DateTime(timezone=True),
        nullable=nullable,
        server_default=sa.text("now()") if default_now else None,
    )


def upgrade() -> None:
    op.create_table(
        "karr_agents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column(
            "token_encrypted", sa.Text(), nullable=False, server_default=sa.text("''")
        ),
        sa.Column(
            "status", sa.Text(), nullable=False, server_default=sa.text("'offline'")
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('online', 'offline', 'unauthorized')",
            name="ck_karr_agents_status",
        ),
    )
    op.create_table(
        "karr_projects",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "description", sa.Text(), nullable=False, server_default=sa.text("''")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_table(
        "karr_environments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("karr_projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("karr_agents.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("image", sa.Text(), nullable=False),
        sa.Column(
            "container_id", sa.Text(), nullable=False, server_default=sa.text("''")
        ),
        sa.Column(
            "status", sa.Text(), nullable=False, server_default=sa.text("'creating'")
        ),
        sa.Column(
            "status_message", sa.Text(), nullable=False, server_default=sa.text("''")
        ),
        sa.Column("gpu", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "env",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "mounts",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "command",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("agent_id", "name", name="uq_karr_environments_agent_name"),
        sa.CheckConstraint(
            "status IN ('creating', 'running', 'stopped', 'error')",
            name="ck_karr_environments_status",
        ),
    )
    op.create_index("idx_karr_environments_agent_id", "karr_environments", ["agent_id"])
    op.create_index(
        "idx_karr_environments_project_id", "karr_environments", ["project_id"]
    )
    op.create_table(
        "karr_agent_registrations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("label", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "status", sa.Text(), nullable=False, server_default=sa.text("'pending'")
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("karr_agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'claimed', 'expired')",
            name="ck_karr_agent_registrations_status",
        ),
    )
    op.create_index(
        "idx_registrations_pending_expires",
        "karr_agent_registrations",
        ["expires_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        "idx_registrations_pending_expires", table_name="karr_agent_registrations"
    )
    op.drop_table("karr_agent_registrations")
    op.drop_index("idx_karr_environments_project_id", table_name="karr_environments")
    op.drop_index("idx_karr_environments_agent_id", table_name="karr_environments")
    op.drop_table("karr_environments")
    op.drop_table("karr_projects")
    op.drop_table("karr_agents")
