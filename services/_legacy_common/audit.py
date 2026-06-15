"""
services/_legacy_common/audit.py — Shared audit base for legacy adapters (I-24).

BaseAuditRecord: common fields present in every adapter's audit trail.
AuditTrail: append-only wrapper — I-24 guarantees no mutation after append.

Canon: ADR-025 §15-16 | I-24 | Phase 5 tranche 3
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class BaseAuditRecord(BaseModel, frozen=True):
    """
    Common audit record fields shared by all legacy adapter audit trails (I-24).

    Subclasses add domain-specific fields (e.g. payment_id, workflow_id).
    record_id holds the domain entity identifier (payment_id, workflow_id, tx_id, …).
    """

    record_id: str
    customer_id: str | None
    event_type: str
    occurred_at: datetime
    status_from: str | None
    status_to: str | None
    metadata: dict[str, Any] | None = None

    model_config = {"arbitrary_types_allowed": True}


class AuditTrail:
    """
    Append-only audit trail container (I-24).

    Once a record is appended it cannot be modified or removed.
    .records() returns a shallow copy so callers cannot mutate internal state.
    """

    def __init__(self) -> None:
        self._records: list[BaseAuditRecord] = []

    def add(self, record: BaseAuditRecord) -> None:
        self._records.append(record)

    def records(self) -> list[BaseAuditRecord]:
        return list(self._records)
