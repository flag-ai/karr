"""Database layer: SQLAlchemy models, sessions and packaged Alembic migrations."""

from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

__all__ = ["MIGRATIONS_DIR"]
