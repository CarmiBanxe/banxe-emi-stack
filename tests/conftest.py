"""
tests/conftest.py — shared fixtures for the test suite
IL-046 | banxe-emi-stack

Provides a fresh in-memory SQLite DB (via SQLAlchemy async) for every test
that touches the auth or customers routers.  Tests that don't use `db_session`
are completely unaffected.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.deps import get_db
from api.main import app
from services.database import Base

# Use in-memory SQLite for tests — fast, isolated, no external deps
_TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the whole session (pytest-asyncio compatibility)."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture()
def db_session(event_loop):
    """
    Yields an AsyncSession backed by an in-memory SQLite DB.
    Creates all tables before the test; drops everything after.
    Override app's get_db dependency for the duration of the test.
    """
    engine = create_async_engine(_TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _setup():
        async with engine.begin() as conn:
            # Register ORM models then create tables
            from api.db import models as _  # noqa: F401

            await conn.run_sync(Base.metadata.create_all)

    async def _teardown():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    event_loop.run_until_complete(_setup())

    async def _override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    yield session_factory
    app.dependency_overrides.pop(get_db, None)
    event_loop.run_until_complete(_teardown())
