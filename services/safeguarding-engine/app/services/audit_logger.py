"""Immutable audit logger for ClickHouse.

All safeguarding events are stored in ClickHouse with 7-year TTL
for FCA regulatory compliance. Records are append-only and immutable.
"""
import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AuditLogger:
    """Immutable audit trail writer for ClickHouse."""

    def __init__(self, clickhouse_client: Any = None):
        self.client = clickhouse_client

    async def log_event(
        self,
        event_type: str,
        entity_type: str,
        entity_id: uuid.UUID,
        action: str,
        actor: str = "system",
        details: str = "",
        position_date: Optional[date] = None,
        amount: Optional[Decimal] = None,
    ) -> uuid.UUID:
        """Write immutable audit event to ClickHouse."""
        event_id = uuid.uuid4()
        logger.info(
            "Audit event: %s/%s/%s by %s",
            event_type, entity_type, action, actor,
        )
        # TODO: Insert into ClickHouse safeguarding_audit table
        raise NotImplementedError("Implement in Phase 3.6")

    async def query_events(
        self,
        event_type: Optional[str] = None,
        entity_type: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """Query audit events from ClickHouse."""
        raise NotImplementedError("Implement in Phase 3.6")

    async def generate_fca_report(
        self, start_date: date, end_date: date
    ) -> Dict:
        """Generate FCA-producible audit report."""
        raise NotImplementedError("Implement in Phase 3.6")
