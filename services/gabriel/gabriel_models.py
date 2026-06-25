"""
services/gabriel/gabriel_models.py
K-gabriel domain models and Protocol ports.

K-gabriel spec §2: SubmissionRecord is the core entity — append-only (I-24),
TTL 5 years (I-08), idempotency keyed by (return_type, return_period).

I-01: No monetary fields at this layer — amounts flow via FinRepSourcePort.
I-24: Submission audit entries are NEVER updated or deleted.
I-27: GabrielSubmissionPort.submit() is ONLY called after HITL sign-off.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable
from uuid import uuid4

# ── Enums ──────────────────────────────────────────────────────────────────────


class GabrielReturnType(str, Enum):
    FIN060 = "FIN060"  # FCA CASS 15 monthly safeguarding return — SUP 16
    BREACH_REPORT = "BREACH_REPORT"  # ad-hoc breach notification — PS23/3 §5


class GabrielReturnStatus(str, Enum):
    DRAFT = "DRAFT"  # created, awaiting validation
    PREPARED = "PREPARED"  # validated, awaiting HITL sign-off
    HITL_PENDING = "HITL_PENDING"  # submitted for human approval
    APPROVED = "APPROVED"  # human approved, ready to submit to FCA
    SUBMITTED = "SUBMITTED"  # sent to Gabriel
    ACCEPTED = "ACCEPTED"  # FCA accepted
    REJECTED = "REJECTED"  # FCA rejected — re-prepare required


# ── Data classes ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SubmissionRecord:
    """Append-only record of a Gabriel return submission (I-24, TTL 5Y I-08).

    Fields mirror K-gabriel spec §3.1 submission record schema.
    """

    submission_id: str
    return_type: GabrielReturnType
    return_period: str  # ISO period "YYYY-MM" for monthly, "YYYY-MM-DD" for breach
    fca_item_code: str  # Gabriel FCA item code e.g. "FIN060-MONTHLY"
    prepared_at: str  # ISO-8601 datetime UTC
    validated_by: str  # user/system id that validated
    status: GabrielReturnStatus
    idempotency_key: str  # "{return_type}:{return_period}" — unique per period
    submitted_at: str | None = None  # ISO-8601 datetime UTC, set on submission
    submission_ref: str | None = None  # FCA reference number, set on acceptance
    source_recon_id: str | None = None  # recon_id if triggered by D-recon breach


@dataclass(frozen=True)
class ReturnSchedule:
    """Config-driven return schedule entry."""

    return_type: GabrielReturnType
    frequency: str  # "MONTHLY" | "AD_HOC"
    deadline_day: int  # day-of-month deadline (e.g. 15 for FIN060)
    fca_item_code: str


@dataclass(frozen=True)
class DeadlineStatus:
    """Deadline status for a pending return."""

    return_type: GabrielReturnType
    return_period: str
    deadline_date: str  # ISO date
    days_remaining: int  # negative = overdue
    is_overdue: bool


@dataclass(frozen=True)
class GabrielAuditEntry:
    """Immutable audit entry for a Gabriel submission event (I-24)."""

    entry_id: str = field(default_factory=lambda: str(uuid4()))
    submission_id: str = ""
    action: str = ""  # "DRAFT_CREATED" | "PREPARED" | "HITL_SUBMITTED" | "SUBMITTED" | "ACCEPTED"
    actor: str = ""  # user/system
    occurred_at: str = ""  # ISO-8601 datetime UTC
    details: str = ""


# ── Ports (Protocol DI) ────────────────────────────────────────────────────────


@runtime_checkable
class GabrielSubmissionPort(Protocol):
    """Port for submitting approved returns to FCA Gabriel / RegData.

    ONLY called after HITL sign-off (I-27). Never call autonomously.
    """

    def submit(self, record: SubmissionRecord) -> SubmissionRecord: ...


@runtime_checkable
class GabrielAuditPort(Protocol):
    """Port for appending Gabriel submission audit entries (I-24).

    Implementations MUST be append-only — no UPDATE or DELETE permitted.
    """

    def record(self, entry: GabrielAuditEntry) -> None: ...


class InMemoryGabrielSubmissionPort:
    """Test stub — records submissions, returns a SUBMITTED copy."""

    def __init__(self) -> None:
        self.submitted: list[SubmissionRecord] = []

    def submit(self, record: SubmissionRecord) -> SubmissionRecord:
        from dataclasses import replace
        from datetime import UTC, datetime

        submitted = replace(
            record,
            status=GabrielReturnStatus.SUBMITTED,
            submitted_at=datetime.now(UTC).isoformat(),
            submission_ref=f"FCA-REF-{record.submission_id[:8].upper()}",
        )
        self.submitted.append(submitted)
        return submitted


class InMemoryGabrielAuditPort:
    """Test stub — accumulates audit entries in order for assertion."""

    def __init__(self) -> None:
        self.entries: list[GabrielAuditEntry] = []

    def record(self, entry: GabrielAuditEntry) -> None:
        self.entries.append(entry)
