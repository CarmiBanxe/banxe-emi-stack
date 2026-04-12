"""Dependency injection: DB sessions, Redis, ClickHouse."""

from typing import AsyncIterator

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
import clickhouse_connect
import structlog

from app.config import get_settings

logger = structlog.get_logger()

# --- Database ---
_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db() -> None:
    """Create async engine and session factory."""
    global _engine, _session_factory
    settings = get_settings()
    _engine = create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        echo=settings.debug,
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    logger.info("db.initialized")


async def close_db() -> None:
    """Dispose engine."""
    global _engine
    if _engine:
        await _engine.dispose()
        logger.info("db.closed")


async def get_db() -> AsyncIterator[AsyncSession]:
    """Yield an async DB session."""
    assert _session_factory is not None, "DB not initialized"
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# --- Redis ---
_redis: aioredis.Redis | None = None


async def init_redis() -> None:
    """Create Redis connection."""
    global _redis
    settings = get_settings()
    _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    logger.info("redis.initialized")


async def close_redis() -> None:
    """Close Redis connection."""
    global _redis
    if _redis:
        await _redis.aclose()
        logger.info("redis.closed")


async def get_redis() -> aioredis.Redis:
    """Return Redis client."""
    assert _redis is not None, "Redis not initialized"
    return _redis


# --- ClickHouse ---
def get_clickhouse_client():
    """Return a ClickHouse client for audit logging."""
    settings = get_settings()
    return clickhouse_connect.get_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        database=settings.clickhouse_database,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
    )
