"""Audit event model for ClickHouse immutable audit trail."""

import uuid
from datetime import UTC, datetime, date
from decimal import Decimal
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AuditEvent:
    """Immutable audit event stored in ClickHouse (7-year TTL)."""

    event_id: uuid.UUID = field(default_factory=uuid.uuid4)
    event_type: str = ""
    entity_type: str = ""
    entity_id: Optional[uuid.UUID] = None
    action: str = ""
    actor: str = "system"
    details: str = ""
    position_date: Optional[date] = None
    amount: Decimal = Decimal("0.00")
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict:
        """Serialize for ClickHouse insertion."""
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "entity_type": self.entity_type,
            "entity_id": str(self.entity_id) if self.entity_id else "",
            "action": self.action,
            "actor": self.actor,
            "details": self.details,
            "position_date": self.position_date.isoformat() if self.position_date else "",
            "amount": float(self.amount),
            "timestamp": self.timestamp.isoformat(),
        }
