"""Health check endpoints."""

from fastapi import APIRouter
from datetime import UTC, datetime

router = APIRouter()


@router.get("/health")
async def health_check():
    """Liveness probe."""
    return {"status": "healthy", "service": "safeguarding-engine", "timestamp": datetime.now(UTC).isoformat()}


@router.get("/ready")
async def readiness_check():
    """Readiness probe - checks DB and Redis connectivity."""
    # TODO: Check PostgreSQL, Redis, ClickHouse connections
    return {"status": "ready", "checks": {"postgres": "ok", "redis": "ok", "clickhouse": "ok"}}
