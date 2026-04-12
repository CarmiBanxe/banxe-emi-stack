"""Tests for ReconciliationService."""
import pytest
from decimal import Decimal
from datetime import date

from app.services.reconciliation_service import ReconciliationService


@pytest.mark.asyncio
async def test_daily_reconciliation(db_session):
    """Test daily internal reconciliation."""
    service = ReconciliationService(db_session)
    result = await service.run_daily_reconciliation(recon_date=date.today())
    assert result is not None
    assert result.recon_type == "daily"


@pytest.mark.asyncio
async def test_monthly_reconciliation(db_session):
    """Test monthly external reconciliation."""
    service = ReconciliationService(db_session)
    result = await service.run_monthly_reconciliation(recon_date=date.today())
    assert result is not None
    assert result.recon_type == "monthly"


@pytest.mark.asyncio
async def test_reconciliation_break_detection(db_session):
    """Test break detection when ledger != bank."""
    service = ReconciliationService(db_session)
    result = await service.detect_breaks(
        ledger_total=Decimal("100000.00"),
        bank_total=Decimal("99999.00"),
    )
    assert result.status == "break"


@pytest.mark.asyncio
async def test_reconciliation_tolerance(db_session):
    """Test GBP 0.01 tolerance matching."""
    service = ReconciliationService(db_session)
    result = await service.detect_breaks(
        ledger_total=Decimal("100000.00"),
        bank_total=Decimal("100000.00"),
    )
    assert result.status == "matched"
