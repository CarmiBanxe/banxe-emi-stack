"""Breach management API endpoints."""

import uuid
from fastapi import APIRouter, Depends

from app.schemas.breach import BreachCreate, BreachResponse, BreachResolve, BreachListResponse
from app.dependencies import get_breach_service

router = APIRouter(prefix="/breaches")


@router.post("", response_model=BreachResponse)
async def report_breach(data: BreachCreate, service=Depends(get_breach_service)):
    """Report a safeguarding breach."""
    return await service.report_breach(data)


@router.get("", response_model=BreachListResponse)
async def list_breaches(active_only: bool = False, severity: str = None, service=Depends(get_breach_service)):
    """List all breaches with filters."""
    return await service.list_breaches(active_only=active_only, severity=severity)


@router.get("/{breach_id}", response_model=BreachResponse)
async def get_breach(breach_id: uuid.UUID, service=Depends(get_breach_service)):
    """Breach detail + remediation timeline."""
    return await service.get_breach(breach_id)


@router.put("/{breach_id}/resolve", response_model=BreachResponse)
async def resolve_breach(breach_id: uuid.UUID, data: BreachResolve, service=Depends(get_breach_service)):
    """Mark breach as resolved."""
    return await service.resolve_breach(breach_id, data)
