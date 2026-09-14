"""SQLAlchemy declarative base. Tables arrive with the schema PR (K2)."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
