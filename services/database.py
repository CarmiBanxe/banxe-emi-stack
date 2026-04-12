"""
services/database.py — Async SQLAlchemy engine + session factory
IL-046 | banxe-emi-stack

DATABASE_URL examples:
  sqlite+aiosqlite:///./banxe_dev.db        — local dev (default)
  sqlite+aiosqlite:///:memory:              — in-memory (tests)
  postgresql+asyncpg://user:pw@host/db      — production

Usage in FastAPI routes:
  async def route(db: AsyncSession = Depends(get_db)):
      result = await db.execute(select(Customer))
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
import os

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./banxe_dev.db",
)

# connect_args only needed for SQLite (check_same_thread=False)
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_async_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields an async DB session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_all_tables() -> None:
    """Create all tables (dev / test helper — use Alembic in production)."""
    async with engine.begin() as conn:
        from api.db import models as _  # noqa: F401 — register ORM models

        await conn.run_sync(Base.metadata.create_all)
