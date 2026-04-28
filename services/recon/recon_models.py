"""
services/recon/recon_models.py
Reconciliation domain models for FCA CASS 7 daily safeguarding recon (IL-SAF-01).

I-01: All monetary values are Decimal — never float.
I-24: Immutable records via frozen dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum


class ReconStatus(str, Enum):
    """Status of a reconciliation run."""

    BALANCED = "BALANCED"
    DISCREPANCY = "DISCREPANCY"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"
    PENDING = "PENDING"


class DiscrepancyType(str, Enum):
    """Type of discrepancy found during reconciliation."""

    SHORTFALL = "SHORTFALL"
    SURPLUS = "SURPLUS"
    MISSING_ENTRY = "MISSING_ENTRY"
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"


class EscalationLevel(str, Enum):
    """Escalation level for discrepancies (I-27)."""

    NONE = "NONE"
    ALERT = "ALERT"
    HITL_MLRO = "HITL_MLRO"
    FCA_NOTIFY = "FCA_NOTIFY"


# Tolerance for penny-exact matching (FCA CASS 7).
RECON_TOLERANCE: Decimal = Decimal("0.01")

# Large value threshold for flagging (I-04).
LARGE_VALUE_THRESHOLD: Decimal = Decimal("50000")

# Blocked jurisdictions (I-02).
BLOCKED_JURISDICTIONS: frozenset[str] = frozenset({
    "RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY",
})


@dataclass(frozen=True)
class AccountBalance:
    """A single account balance snapshot."""

    account_id: str
    account_name: str
    balance: Decimal  # I-01
    currency: str
    jurisdiction: str = "GB"
    as_of: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def __post_init__(self) -> None:
        if not isinstance(self.balance, Decimal):
            raise TypeError(
                f"balance must be Decimal, got {type(self.balance).__name__} (I-01)"
            )


@dataclass(frozen=True)
class Discrepancy:
    """A discrepancy found during reconciliation (I-24 immutable)."""

    discrepancy_id: str
    discrepancy_type: DiscrepancyType
    expected: Decimal  # I-01
    actual: Decimal    # I-01
    difference: Decimal  # I-01
    account_id: str
    description: str
    escalation_level: EscalationLevel = EscalationLevel.NONE

    def __post_init__(self) -> None:
        for fld in ("expected", "actual", "difference"):
            val = getattr(self, fld)
            if not isinstance(val, Decimal):
                raise TypeError(
                    f"{fld} must be Decimal, got {type(val).__name__} (I-01)"
                )


@dataclass(frozen=True)
class ReconResult:
    """Result of a daily reconciliation run (I-24 immutable)."""

    recon_id: str
    recon_date: str
    status: ReconStatus
    client_funds_total: Decimal  # I-01
    safeguarding_total: Decimal  # I-01
    difference: Decimal          # I-01
    discrepancies: tuple[Discrepancy, ...] = ()
    large_values_flagged: int = 0
    excluded_jurisdictions: tuple[str, ...] = ()
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def __post_init__(self) -> None:
        for fld in ("client_funds_total", "safeguarding_total", "difference"):
            val = getattr(self, fld)
            if not isinstance(val, Decimal):
                raise TypeError(
                    f"{fld} must be Decimal, got {type(val).__name__} (I-01)"
                )


@dataclass(frozen=True)
class ReconAuditEntry:
    """Immutable audit record for reconciliation events (I-24)."""

    recon_id: str
    action: str
    status: ReconStatus
    client_funds_total: Decimal  # I-01
    safeguarding_total: Decimal  # I-01
    actor: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    details: str = ""
