"""
services/ledger/approval_models.py
High-value posting approval audit (I-04 high-value, I-24 append-only, I-27 HITL).

A high-value journal entry (>= HIGH_VALUE_THRESHOLD) is never auto-posted: it is
recorded PENDING and requires a named human approver to APPROVE (which posts it)
or REJECT (which does not). The store is append-only — a decision appends a new
row, never mutating the PENDING record (I-24).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol


class ApprovalDecision(str, Enum):
    """State of a high-value approval."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class HighValueApproval:
    """Immutable audit row for a high-value approval (I-01 Decimal, I-24)."""

    proposal_id: str
    entry_id: str
    total_amount: Decimal  # I-01
    currency: str
    requested_by: str
    decision: ApprovalDecision = ApprovalDecision.PENDING
    approver: str | None = None
    reason: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    decided_at: str | None = None


class ApprovalStorePort(Protocol):
    """Append-only store for high-value approval audit rows (I-24)."""

    def record(self, approval: HighValueApproval) -> None: ...

    def get(self, proposal_id: str) -> HighValueApproval | None: ...


class InMemoryApprovalStore:
    """Append-only in-memory approval audit trail (I-24)."""

    def __init__(self) -> None:
        self._records: list[HighValueApproval] = []

    def record(self, approval: HighValueApproval) -> None:
        # Append-only: a decision is a NEW row; the PENDING row is never mutated.
        self._records.append(approval)

    def get(self, proposal_id: str) -> HighValueApproval | None:
        matches = [r for r in self._records if r.proposal_id == proposal_id]
        return matches[-1] if matches else None

    @property
    def records(self) -> list[HighValueApproval]:
        return list(self._records)
