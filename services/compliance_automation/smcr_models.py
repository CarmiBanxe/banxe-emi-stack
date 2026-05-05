"""
services/compliance_automation/smcr_models.py
SMCR (Senior Managers & Certification Regime) domain models (IL-GOV-01).

FCA SMCR requires EMI firms to:
- Register Senior Management Functions (SMFs)
- Certify relevant staff annually
- Enforce Conduct Rules
- Report breaches to FCA

I-24: Immutable records via frozen dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class SMFRole(str, Enum):
    """FCA Senior Management Functions relevant to EMI."""

    SMF1 = "SMF1"  # Chief Executive
    SMF3 = "SMF3"  # Executive Director
    SMF9 = "SMF9"  # Chair
    SMF16 = "SMF16"  # Compliance Oversight
    SMF17 = "SMF17"  # Money Laundering Reporting Officer (MLRO)
    SMF24 = "SMF24"  # Chief Operations
    SMF27 = "SMF27"  # Partner
    SMF29 = "SMF29"  # Limited Scope (small firms)


class CertificationStatus(str, Enum):
    """Annual certification status."""

    CERTIFIED = "CERTIFIED"
    PENDING = "PENDING"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class ConductRuleTier(str, Enum):
    """FCA Conduct Rules tiers."""

    TIER_1 = "TIER_1"  # Individual Conduct Rules (all staff)
    TIER_2 = "TIER_2"  # Senior Manager Conduct Rules (SMFs only)


class BreachSeverity(str, Enum):
    """Severity of a conduct rule breach."""

    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"


class BreachStatus(str, Enum):
    """Status of a breach report."""

    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    REPORTED_TO_FCA = "REPORTED_TO_FCA"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class SeniorManager:
    """Registered Senior Management Function holder (I-24 immutable)."""

    person_id: str
    name: str
    role: SMFRole
    fca_reference: str  # FCA Individual Reference Number (IRN)
    appointed_at: str
    statement_of_responsibilities: str  # SoR document reference
    is_active: bool = True
    registered_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(frozen=True)
class CertifiedPerson:
    """Certified person under SMCR Certification Regime (I-24 immutable)."""

    person_id: str
    name: str
    function_title: str
    certification_status: CertificationStatus
    certified_at: str
    expires_at: str  # Annual renewal required
    certified_by: str  # Person ID of certifying senior manager
    registered_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(frozen=True)
class ConductRule:
    """FCA Conduct Rule definition (I-24 immutable)."""

    rule_id: str
    tier: ConductRuleTier
    title: str
    description: str


@dataclass(frozen=True)
class BreachReport:
    """Conduct rule breach report (I-24 immutable)."""

    breach_id: str
    person_id: str
    rule_id: str
    severity: BreachSeverity
    status: BreachStatus
    description: str
    reported_by: str
    reported_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    fca_notified: bool = False


@dataclass(frozen=True)
class SMCRAuditEntry:
    """Immutable audit entry for SMCR operations (I-24)."""

    action: str
    entity_type: str  # "SENIOR_MANAGER", "CERTIFIED_PERSON", "BREACH"
    entity_id: str
    actor: str
    details: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


# FCA Individual Conduct Rules (Tier 1 — all SMCR staff).
INDIVIDUAL_CONDUCT_RULES: tuple[ConductRule, ...] = (
    ConductRule("ICR-1", ConductRuleTier.TIER_1, "Integrity", "Act with integrity"),
    ConductRule(
        "ICR-2",
        ConductRuleTier.TIER_1,
        "Due skill, care and diligence",
        "Act with due skill, care and diligence",
    ),
    ConductRule(
        "ICR-3",
        ConductRuleTier.TIER_1,
        "Open and cooperative",
        "Be open and cooperative with regulators",
    ),
    ConductRule(
        "ICR-4",
        ConductRuleTier.TIER_1,
        "Proper standards of market conduct",
        "Pay due regard to proper standards of market conduct",
    ),
    ConductRule(
        "ICR-5",
        ConductRuleTier.TIER_1,
        "Responsible behaviour",
        "Act in a way that promotes the integrity of the UK financial system",
    ),
)

# Senior Manager Conduct Rules (Tier 2 — SMFs only).
SENIOR_MANAGER_CONDUCT_RULES: tuple[ConductRule, ...] = (
    ConductRule(
        "SMCR-1",
        ConductRuleTier.TIER_2,
        "Reasonable steps (business)",
        "Take reasonable steps to ensure business is controlled effectively",
    ),
    ConductRule(
        "SMCR-2",
        ConductRuleTier.TIER_2,
        "Reasonable steps (compliance)",
        "Take reasonable steps to ensure compliance with regulatory requirements",
    ),
    ConductRule(
        "SMCR-3",
        ConductRuleTier.TIER_2,
        "Reasonable steps (delegation)",
        "Take reasonable steps to ensure any delegation is to an appropriate person",
    ),
    ConductRule(
        "SMCR-4",
        ConductRuleTier.TIER_2,
        "Disclose information",
        "Disclose appropriately any information the FCA would reasonably expect notice of",
    ),
)
