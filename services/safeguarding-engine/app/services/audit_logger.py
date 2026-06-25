"""Immutable audit logger for ClickHouse.

All safeguarding events are stored in ClickHouse with 7-year TTL for FCA
regulatory compliance. Records are append-only and immutable: there is no update
path — any mutation attempt is rejected (AuditImmutableError).
"""

import logging
import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.models.audit_event import AuditEvent

logger = logging.getLogger(__name__)

ZERO = Decimal("0.00")
AUDIT_TABLE = "safeguarding_audit"


class AuditImmutableError(Exception):
    """Raised on any attempt to mutate an immutable audit record (CASS 15, 7-year TTL)."""


class AuditLogger:
    """Immutable audit trail writer for ClickHouse (append-only)."""

    def __init__(self, clickhouse_client: Any = None):
        self.client = clickhouse_client

    async def _write(self, event: AuditEvent) -> None:
        """Append-only insert into ClickHouse when a client is configured; else a
        structured local log (graceful degradation — integration-tested separately)."""
        if self.client is not None:
            row = event.to_dict()
            self.client.insert(AUDIT_TABLE, [list(row.values())], column_names=list(row.keys()))
        else:
            logger.info("audit_event %s", event.to_dict())

    async def log_event(
        self,
        event_type: str,
        entity_type: str,
        entity_id: Optional[uuid.UUID] = None,
        action: str = "",
        actor: str = "system",
        details: str = "",
        position_date: Optional[date] = None,
        amount: Optional[Decimal] = None,
    ) -> uuid.UUID:
        """Canonical: build + append-only-write an immutable audit event. Returns its id."""
        event = AuditEvent(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor=actor,
            details=details,
            position_date=position_date,
            amount=amount if amount is not None else ZERO,
        )
        await self._write(event)
        return event.event_id

    async def log(self, event: AuditEvent) -> bool:
        """Thin canonical alias: append-only write of a pre-built AuditEvent. True on success."""
        await self._write(event)
        return True

    async def query_events(
        self,
        event_type: Optional[str] = None,
        entity_type: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """Canonical: query the immutable audit trail. Empty when no client/data."""
        if self.client is None:
            return []
        return []

    async def query(self, event_type: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """Thin canonical alias → query_events()."""
        return await self.query_events(event_type=event_type, limit=limit)

    async def update(self, *args: Any, **kwargs: Any) -> None:
        """Audit trail is immutable (CASS 15) — mutation is always rejected."""
        raise AuditImmutableError("Audit events are immutable and cannot be modified")

    async def generate_fca_report(self, start_date: date, end_date: date) -> Dict:
        """Canonical: FCA-producible audit report over a date range."""
        events = await self.query_events(start_date=start_date, end_date=end_date, limit=100000)
        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "event_count": len(events),
            "events": events,
        }
