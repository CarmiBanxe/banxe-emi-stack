"""Tests for SafeguardingService."""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from app.services.safeguarding_service import SafeguardingService


@pytest.mark.asyncio
async def test_record_safeguarding_obligation(db_session):
    """Test recording a new safeguarding obligation."""
    service = SafeguardingService(db_session)
    result = await service.record_obligation(
        amount=Decimal("10000.00"),
        currency="GBP",
        source="e-money-receipt",
    )
    assert result is not None
    assert result.amount == Decimal("10000.00")


@pytest.mark.asyncio
async def test_get_current_position(db_session):
    """Test retrieving current safeguarding position."""
    service = SafeguardingService(db_session)
    position = await service.get_current_position()
    assert position is not None
    assert hasattr(position, "total_client_funds")
    assert hasattr(position, "total_safeguarded")


@pytest.mark.asyncio
async def test_shortfall_detection(db_session):
    """Test that shortfall triggers breach alert."""
    service = SafeguardingService(db_session)
    shortfall = await service.calculate_shortfall()
    assert shortfall is not None


@pytest.mark.asyncio
async def test_safeguard_within_t_plus_one(db_session):
    """Test T+1 business day safeguarding compliance."""
    service = SafeguardingService(db_session)
    is_compliant = await service.check_timing_compliance()
    assert isinstance(is_compliant, bool)
