"""Declarative base and shared database column helpers."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def new_uuid() -> str:
    """Return a portable UUID string suitable for SQLite and PostgreSQL."""

    return str(uuid4())


def utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""

    return datetime.now(UTC)
