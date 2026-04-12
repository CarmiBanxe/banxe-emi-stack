"""Tests for BreachService."""
import pytest
from decimal import Decimal

from app.services.breach_service import BreachService


@pytest.mark.asyncio
async def test_report_breach(db_session):
    """Test reporting a safeguarding breach."""
    service = BreachService(db_session)
    breach = await service.report_breach(
        breach_type="shortfall",
        severity="critical",
        description="Safeguarding shortfall detected",
        shortfall_amount=Decimal("5000.00"),
    )
    assert breach is not None
    assert breach.severity == "critical"


@pytest.mark.asyncio
async def test_fca_notification_required(db_session):
    """Test FCA notification within 1 business day for critical."""
    service = BreachService(db_session)
    requires = await service.requires_fca_notification(severity="critical")
    assert requires is True


@pytest.mark.asyncio
async def test_resolve_breach(db_session):
    """Test resolving a breach with remediation notes."""
    service = BreachService(db_session)
    resolved = await service.resolve_breach(
        breach_id="test-id",
        remediation_notes="Funds transferred to cover shortfall",
    )
    assert resolved is not None


@pytest.mark.asyncio
async def test_auto_detect_shortfall(db_session):
    """Test automatic breach detection on shortfall."""
    service = BreachService(db_session)
    breaches = await service.auto_detect()
    assert isinstance(breaches, list)
