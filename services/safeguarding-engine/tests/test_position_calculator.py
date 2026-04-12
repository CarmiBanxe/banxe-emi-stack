"""Tests for PositionCalculator."""

import pytest
from decimal import Decimal

from app.services.position_calculator import PositionCalculator


@pytest.mark.asyncio
async def test_calculate_position(db_session):
    """Test position calculation from Midaz + bank balances."""
    calc = PositionCalculator(db_session)
    position = await calc.calculate()
    assert position is not None


@pytest.mark.asyncio
async def test_shortfall_positive(db_session):
    """Test shortfall when client funds exceed safeguarded."""
    calc = PositionCalculator(db_session)
    shortfall = calc.compute_shortfall(
        client_funds=Decimal("1000000.00"),
        safeguarded=Decimal("950000.00"),
    )
    assert shortfall == Decimal("50000.00")


@pytest.mark.asyncio
async def test_no_shortfall(db_session):
    """Test no shortfall when fully safeguarded."""
    calc = PositionCalculator(db_session)
    shortfall = calc.compute_shortfall(
        client_funds=Decimal("1000000.00"),
        safeguarded=Decimal("1000000.00"),
    )
    assert shortfall == Decimal("0.00")
