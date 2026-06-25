"""Test fixtures for Safeguarding Engine."""

import asyncio
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.main import create_app
from app.config import Settings
from app.dependencies import get_audit_logger, get_clickhouse_client, get_db, get_redis
from app.services.audit_logger import AuditLogger


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
    # create_app() takes no args (settings come from get_settings()).
    application = create_app()
    yield application


@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def async_client(app) -> AsyncGenerator:
    """ASGI test client with infra dependencies overridden (no live DB/Redis/ClickHouse).

    Services are DI-built; their methods operate at the contract level, so a mocked
    session/redis is sufficient to exercise the API surface without live infra.
    """

    async def _override_get_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_redis] = lambda: AsyncMock()
    app.dependency_overrides[get_clickhouse_client] = lambda: None
    # get_audit_logger() calls get_clickhouse_client() directly (not via Depends),
    # so override the provider itself to avoid a live ClickHouse connection.
    app.dependency_overrides[get_audit_logger] = lambda: AuditLogger(clickhouse_client=None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def db_session(settings) -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def redis_client() -> AsyncMock:
    """Mocked Redis client for unit tests (no live Redis). AuditLogger does not use
    Redis directly; this fixture satisfies tests that declare the dependency."""
    return AsyncMock()
