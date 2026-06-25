"""Reconciliation API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends

from app.schemas.reconciliation import (
    DailyReconRequest,
    MonthlyReconRequest,
    ReconciliationResponse,
    ReconciliationDetailResponse,
)
from app.dependencies import get_reconciliation_service

router = APIRouter(prefix="/reconcile")


@router.post("/daily", response_model=ReconciliationResponse)
async def trigger_daily_recon(request: Optional[DailyReconRequest] = None, service=Depends(get_reconciliation_service)):
    """Trigger daily internal reconciliation (defaults to today when no body)."""
    return await service.run_daily_reconciliation(request)


@router.post("/monthly", response_model=ReconciliationResponse)
async def trigger_monthly_recon(
    request: Optional[MonthlyReconRequest] = None, service=Depends(get_reconciliation_service)
):
    """Trigger monthly external reconciliation (defaults to current month when no body)."""
    return await service.run_monthly_reconciliation(request)


@router.get("/history")
async def get_recon_history(recon_type: str = None, limit: int = 50, service=Depends(get_reconciliation_service)):
    """List reconciliation results."""
    return await service.get_history(recon_type=recon_type, limit=limit)


@router.get("/{recon_id}", response_model=ReconciliationDetailResponse)
async def get_recon_detail(recon_id: str, service=Depends(get_reconciliation_service)):
    """Detailed reconciliation report."""
    return await service.get_detail(recon_id)
