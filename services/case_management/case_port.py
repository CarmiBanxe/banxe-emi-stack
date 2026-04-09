"""
services/case_management/case_port.py — Case Management Hexagonal Port
IL-059 | EU AI Act Art.14 (human oversight) | FCA MLR 2017 §26 | banxe-emi-stack

WHY THIS EXISTS
---------------
FCA MLR 2017 §26 and EU AI Act Art.14 require human oversight of AI-driven
risk decisions. When the FraudAML pipeline or AML pipeline flags a transaction
as HIGH/MEDIUM risk, a case must be created for MLRO/compliance review.

Marble (https://checkmarble.com, Apache 2.0, self-hosted on GMKtec :5002)
provides the case management backend: case inbox, assignment, status tracking,
audit trail. This port abstracts Marble away from the rest of the stack.

Case lifecycle:
  OPEN → INVESTIGATING → RESOLVED | CLOSED

Case types (aligned with FCA/PSR requirements):
  SAR           — Suspicious Activity Report (POCA 2002 s.330)
  EDD           — Enhanced Due Diligence trigger (MLR 2017 §33)
  FRAUD_REVIEW  — HITL review of HIGH/MEDIUM fraud score
  APP_SCAM      — PSR APP 2024 scam indicator review
  MLRO_REVIEW   — Generic MLRO sign-off required

Outcome:
  APPROVED      — case resolved, transaction permitted
  REJECTED      — case resolved, transaction blocked / customer action taken
  ESCALATED     — escalated to senior MLRO or external (NCA for SAR)
  INCONCLUSIVE  — insufficient evidence, case closed without determination
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol


class CaseType(str, Enum):
    SAR = "SAR"
    EDD = "EDD"
    FRAUD_REVIEW = "FRAUD_REVIEW"
    APP_SCAM = "APP_SCAM"
    MLRO_REVIEW = "MLRO_REVIEW"


class CasePriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class CaseStatus(str, Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class CaseOutcome(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ESCALATED = "ESCALATED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass
class CaseRequest:
    """
    Request to open a new compliance case.

    case_reference: Banxe internal ID (transaction_id or customer_id)
    case_type: reason the case was opened
    entity_id: customer_id (individual or business)
    entity_type: "individual" or "business"
    priority: derived from risk score (CRITICAL≥85, HIGH≥70, MEDIUM≥40, LOW<40)
    description: human-readable summary for MLRO inbox
    metadata: arbitrary key-value for audit trail (risk_score, factors, etc.)
    """

    case_reference: str
    case_type: CaseType
    entity_id: str
    entity_type: str
    priority: CasePriority
    description: str
    amount: Decimal | None = None
    currency: str | None = None
    risk_score: int | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class CaseResult:
    """
    Result of a case creation or lookup.

    case_id: provider-assigned case identifier (Marble case ID)
    case_reference: Banxe internal reference (mirrors request)
    status: current lifecycle state
    url: direct link to Marble backoffice for MLRO (None if unavailable)
    provider: "marble" | "mock"
    """

    case_id: str
    case_reference: str
    status: CaseStatus
    provider: str
    created_at: datetime
    assigned_to: str | None = None
    outcome: CaseOutcome | None = None
    url: str | None = None


class CaseManagementPort(Protocol):
    """
    Hexagonal port for case management.
    Implementations: MarbleAdapter (production), MockCaseAdapter (dev/test).
    """

    def create_case(self, request: CaseRequest) -> CaseResult:
        """Open a new compliance case. Idempotent on case_reference."""
        ...

    def get_case(self, case_id: str) -> CaseResult:
        """Retrieve current state of a case by provider ID."""
        ...

    def resolve_case(
        self,
        case_id: str,
        outcome: CaseOutcome,
        notes: str = "",
    ) -> CaseResult:
        """
        Close a case with a final outcome.
        Called by MLRO after human review (I-27: human decides, not AI).
        """
        ...

    def health(self) -> bool:
        """Return True if the case management backend is reachable."""
        ...
