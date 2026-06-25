"""Test fixtures for Safeguarding Engine."""

import asyncio
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.main import create_app
from app.config import Settings


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def settings() -> Settings:
    # Use the real Settings field names (app/config.py): lowercase database_url /
    # redis_url, and the split clickhouse_* fields (there is no clickhouse_url).
    # The model keeps extra="forbid", so kwargs must match field names exactly.
    return Settings(
        database_url="postgresql+asyncpg://test:test@localhost:5432/safeguarding_test",
        redis_url="redis://localhost:6379/1",
        clickhouse_host="localhost",
        clickhouse_database="safeguarding_test",
    )


@pytest_asyncio.fixture
async def app(settings):
    application = create_app(settings)
    yield application


@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator:
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session(settings) -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()
