"""Safeguarding core API endpoints."""
from fastapi import APIRouter, Depends
from typing import Optional

from app.schemas.safeguarding import (
    SafeguardingRequest,
    SafeguardingResponse,
    PositionResponse,
    ShortfallResponse,
)
from app.dependencies import get_safeguarding_service

router = APIRouter(prefix="/safeguard")


@router.post("", response_model=SafeguardingResponse)
async def record_safeguarding(request: SafeguardingRequest, service=Depends(get_safeguarding_service)):
    """Record new safeguarding obligation (triggered on e-money receipt)."""
    return await service.record_obligation(request)


@router.get("/positions", response_model=PositionResponse)
async def get_positions(service=Depends(get_safeguarding_service)):
    """Current safeguarding position summary."""
    return await service.get_position()


@router.get("/positions/{date}", response_model=PositionResponse)
async def get_position_by_date(date: str, service=Depends(get_safeguarding_service)):
    """Historical position for specific date."""
    return await service.get_position(position_date=date)


@router.get("/positions/shortfall", response_model=ShortfallResponse)
async def get_shortfall(service=Depends(get_safeguarding_service)):
    """Calculate any shortfall vs required."""
    return await service.get_shortfall()
