"""
api/routers/health.py — Liveness + readiness health check
IL-046 | banxe-emi-stack

GET /health — always 200 if process is alive (liveness)
GET /health/ready — checks downstream services (readiness)
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    status: str
    version: str = "1.0.0"
    plane: str = "Product"


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, str]


@router.get("/health", response_model=HealthResponse, summary="Liveness check")
async def liveness() -> HealthResponse:
    """Returns 200 if the API process is running."""
    return HealthResponse(status="ok")


@router.get(
    "/health/ready", response_model=ReadinessResponse, summary="Readiness check"
)
async def readiness() -> ReadinessResponse:
    """
    Checks downstream service connectivity.
    Returns 200 if all critical dependencies are reachable.
    """
    from api.deps import get_kyc_service, get_payment_service

    checks: dict[str, str] = {}

    # KYC service
    try:
        kyc = get_kyc_service()
        checks["kyc"] = "ok" if kyc.health() else "degraded"
    except Exception:
        checks["kyc"] = "error"

    # Payment service
    try:
        payment = get_payment_service()
        checks["payment"] = "ok" if payment.health_check() else "degraded"
    except Exception:
        checks["payment"] = "error"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return ReadinessResponse(status=overall, checks=checks)
