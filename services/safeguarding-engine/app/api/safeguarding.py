"""Safeguarding core API endpoints."""

from fastapi import APIRouter, Depends

from app.schemas.safeguarding import (
    SafeguardingRequest,
    SafeguardingResponse,
    PositionResponse,
    ShortfallResponse,
)
from app.dependencies import get_safeguarding_service

# No router prefix: the obligation POST lives at /safeguard while positions live at
# /positions (siblings under /api/v1), matching the documented API contract.
router = APIRouter()


@router.post("/safeguard", response_model=SafeguardingResponse)
async def record_safeguarding(request: SafeguardingRequest, service=Depends(get_safeguarding_service)):
    """Record new safeguarding obligation (triggered on e-money receipt)."""
    return await service.record_obligation(request)


@router.get("/positions", response_model=PositionResponse)
async def get_positions(service=Depends(get_safeguarding_service)):
    """Current safeguarding position summary."""
    return await service.get_position()


# NOTE: /positions/shortfall must be declared BEFORE /positions/{date}, otherwise
# the path-parameter route shadows it (date="shortfall").
@router.get("/positions/shortfall", response_model=ShortfallResponse)
async def get_shortfall(service=Depends(get_safeguarding_service)):
    """Calculate any shortfall vs required."""
    return await service.get_shortfall()


@router.get("/positions/{date}", response_model=PositionResponse)
async def get_position_by_date(date: str, service=Depends(get_safeguarding_service)):
    """Historical position for specific date."""
    return await service.get_position(position_date=date)
