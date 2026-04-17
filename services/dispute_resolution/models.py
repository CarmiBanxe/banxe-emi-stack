"""
services/dispute_resolution/models.py — Domain models for Dispute Resolution & Chargeback
IL-DRM-01 | Phase 33 | banxe-emi-stack
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from decimal import Decimal
from enum import Enum
import hashlib
from typing import Protocol, runtime_checkable

_SLA_DAYS = 56  # DISP 1.3 — 8 weeks


class DisputeType(str, Enum):
    UNAUTHORIZED_TRANSACTION = "UNAUTHORIZED_TRANSACTION"
    DUPLICATE_CHARGE = "DUPLICATE_CHARGE"
    MERCHANDISE_NOT_RECEIVED = "MERCHANDISE_NOT_RECEIVED"
    DEFECTIVE_MERCHANDISE = "DEFECTIVE_MERCHANDISE"
    CREDIT_NOT_PROCESSED = "CREDIT_NOT_PROCESSED"


class DisputeStatus(str, Enum):
    OPENED = "OPENED"
    UNDER_INVESTIGATION = "UNDER_INVESTIGATION"
    PENDING_EVIDENCE = "PENDING_EVIDENCE"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    ESCALATED = "ESCALATED"


class EvidenceType(str, Enum):
    RECEIPT = "RECEIPT"
    SCREENSHOT = "SCREENSHOT"
    BANK_STATEMENT = "BANK_STATEMENT"
    COMMUNICATION = "COMMUNICATION"
    PHOTO = "PHOTO"


class ResolutionOutcome(str, Enum):
    UPHELD = "UPHELD"
    REJECTED = "REJECTED"
    PARTIAL_REFUND = "PARTIAL_REFUND"
    WITHDRAWN = "WITHDRAWN"


class EscalationLevel(str, Enum):
    LEVEL_1 = "LEVEL_1"
    LEVEL_2 = "LEVEL_2"
    FOS = "FOS"


def compute_evidence_hash(content: bytes) -> str:
    """SHA-256 hash of evidence content (I-12)."""
    return hashlib.sha256(content).hexdigest()


@dataclasses.dataclass(frozen=True)
class Dispute:
    dispute_id: str
    customer_id: str
    payment_id: str
    dispute_type: DisputeType
    amount: Decimal
    description: str
    status: DisputeStatus
    created_at: datetime
    sla_deadline: datetime
    investigator_id: str = ""
    liability_party: str = ""
    outcome: ResolutionOutcome | None = None
    resolved_at: datetime | None = None


@dataclasses.dataclass(frozen=True)
class DisputeEvidence:
    evidence_id: str
    dispute_id: str
    evidence_type: EvidenceType
    file_hash: str  # SHA-256 (I-12)
    description: str
    submitted_at: datetime


@dataclasses.dataclass(frozen=True)
class ResolutionProposal:
    proposal_id: str
    dispute_id: str
    outcome: ResolutionOutcome
    refund_amount: Decimal | None
    reason: str
    proposed_at: datetime
    approved_by: str = ""
    approved_at: datetime | None = None


@dataclasses.dataclass(frozen=True)
class ChargebackRecord:
    chargeback_id: str
    dispute_id: str
    scheme: str
    amount: Decimal
    reason_code: str
    initiated_at: datetime
    status: str = "INITIATED"


@dataclasses.dataclass(frozen=True)
class EscalationRecord:
    escalation_id: str
    dispute_id: str
    level: EscalationLevel
    reason: str
    escalated_at: datetime
    resolved_at: datetime | None = None


@runtime_checkable
class DisputePort(Protocol):
    def save(self, dispute: Dispute) -> None: ...
    def get(self, dispute_id: str) -> Dispute | None: ...
    def update(self, dispute: Dispute) -> None: ...
    def list_by_customer(self, customer_id: str) -> list[Dispute]: ...


@runtime_checkable
class EvidencePort(Protocol):
    def save(self, evidence: DisputeEvidence) -> None: ...
    def list_by_dispute(self, dispute_id: str) -> list[DisputeEvidence]: ...


@runtime_checkable
class ResolutionPort(Protocol):
    def save(self, proposal: ResolutionProposal) -> None: ...
    def get(self, proposal_id: str) -> ResolutionProposal | None: ...
    def update(self, proposal: ResolutionProposal) -> None: ...


@runtime_checkable
class ChargebackPort(Protocol):
    def save(self, record: ChargebackRecord) -> None: ...
    def get(self, chargeback_id: str) -> ChargebackRecord | None: ...
    def list_by_dispute(self, dispute_id: str) -> list[ChargebackRecord]: ...


@runtime_checkable
class EscalationPort(Protocol):
    def save(self, record: EscalationRecord) -> None: ...
    def list_by_dispute(self, dispute_id: str) -> list[EscalationRecord]: ...


class InMemoryDisputeStore:
    def __init__(self) -> None:
        self._data: dict[str, Dispute] = {}

    def save(self, dispute: Dispute) -> None:
        self._data[dispute.dispute_id] = dispute

    def get(self, dispute_id: str) -> Dispute | None:
        return self._data.get(dispute_id)

    def update(self, dispute: Dispute) -> None:
        self._data[dispute.dispute_id] = dispute

    def list_by_customer(self, customer_id: str) -> list[Dispute]:
        return [d for d in self._data.values() if d.customer_id == customer_id]


class InMemoryEvidenceStore:
    """Append-only evidence store (I-24)."""

    def __init__(self) -> None:
        self._records: list[DisputeEvidence] = []

    def save(self, evidence: DisputeEvidence) -> None:
        self._records.append(evidence)

    def list_by_dispute(self, dispute_id: str) -> list[DisputeEvidence]:
        return [e for e in self._records if e.dispute_id == dispute_id]


class InMemoryResolutionStore:
    def __init__(self) -> None:
        self._data: dict[str, ResolutionProposal] = {}

    def save(self, proposal: ResolutionProposal) -> None:
        self._data[proposal.proposal_id] = proposal

    def get(self, proposal_id: str) -> ResolutionProposal | None:
        return self._data.get(proposal_id)

    def update(self, proposal: ResolutionProposal) -> None:
        self._data[proposal.proposal_id] = proposal


class InMemoryChargebackStore:
    def __init__(self) -> None:
        self._data: dict[str, ChargebackRecord] = {}

    def save(self, record: ChargebackRecord) -> None:
        self._data[record.chargeback_id] = record

    def get(self, chargeback_id: str) -> ChargebackRecord | None:
        return self._data.get(chargeback_id)

    def list_by_dispute(self, dispute_id: str) -> list[ChargebackRecord]:
        return [r for r in self._data.values() if r.dispute_id == dispute_id]


class InMemoryEscalationStore:
    """Append-only escalation store (I-24)."""

    def __init__(self) -> None:
        self._records: list[EscalationRecord] = []

    def save(self, record: EscalationRecord) -> None:
        self._records.append(record)

    def list_by_dispute(self, dispute_id: str) -> list[EscalationRecord]:
        return [r for r in self._records if r.dispute_id == dispute_id]
