"""Dependency injection: DB sessions, Redis, ClickHouse, service providers."""

from typing import AsyncIterator

import redis.asyncio as aioredis
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
import clickhouse_connect
import structlog

from app.config import get_settings
from app.services.audit_logger import AuditLogger
from app.services.breach_service import BreachService
from app.services.position_calculator import PositionCalculator
from app.services.reconciliation_service import ReconciliationService
from app.services.safeguarding_service import SafeguardingService

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


# --- Service providers (FastAPI Depends wiring) ---
# Wired from the existing infra dependencies above and the service constructors
# (verified signatures). No new infra objects; no business-logic changes.

def get_audit_logger() -> AuditLogger:
    """AuditLogger(clickhouse_client) — shared audit-trail helper."""
    return AuditLogger(clickhouse_client=get_clickhouse_client())


def get_position_calculator(
    db: AsyncSession = Depends(get_db),
    audit_logger: AuditLogger = Depends(get_audit_logger),
) -> PositionCalculator:
    """PositionCalculator(db, audit_logger)."""
    return PositionCalculator(db=db, audit_logger=audit_logger)


def get_breach_service(
    db: AsyncSession = Depends(get_db),
    audit_logger: AuditLogger = Depends(get_audit_logger),
) -> BreachService:
    """BreachService(db, audit_logger)."""
    return BreachService(db=db, audit_logger=audit_logger)


def get_safeguarding_service(
    db: AsyncSession = Depends(get_db),
    audit_logger: AuditLogger = Depends(get_audit_logger),
    breach_service: BreachService = Depends(get_breach_service),
) -> SafeguardingService:
    """SafeguardingService(db, audit_logger, breach_service)."""
    return SafeguardingService(db=db, audit_logger=audit_logger, breach_service=breach_service)


def get_reconciliation_service(
    db: AsyncSession = Depends(get_db),
    audit_logger: AuditLogger = Depends(get_audit_logger),
    breach_service: BreachService = Depends(get_breach_service),
) -> ReconciliationService:
    """ReconciliationService(db, audit_logger, breach_service)."""
    return ReconciliationService(db=db, audit_logger=audit_logger, breach_service=breach_service)
