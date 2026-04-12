"""Tests for AuditLogger (ClickHouse)."""
import pytest
from decimal import Decimal
from datetime import date

from app.services.audit_logger import AuditLogger
from app.models.audit_event import AuditEvent


@pytest.mark.asyncio
async def test_log_event(redis_client):
    """Test logging an audit event to ClickHouse."""
    logger = AuditLogger()
    event = AuditEvent(
        event_type="position_calculated",
        entity_type="position",
        action="create",
        actor="scheduler",
        details="Daily position calculation",
        position_date=date.today(),
        amount=Decimal("1000000.00"),
    )
    result = await logger.log(event)
    assert result is True


@pytest.mark.asyncio
async def test_query_audit_events(redis_client):
    """Test querying audit events."""
    logger = AuditLogger()
    events = await logger.query(event_type="position_calculated", limit=10)
    assert isinstance(events, list)


@pytest.mark.asyncio
async def test_audit_immutability(redis_client):
    """Test that audit events cannot be modified."""
    logger = AuditLogger()
    with pytest.raises(Exception):
        await logger.update(event_id="test", details="modified")
