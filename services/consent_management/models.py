"""
services/consent_management/models.py
Consent Management & TPP Registry — Domain Models
IL-CNS-01 | Phase 49 | Sprint 35

FCA: PSD2 Art.65-67, RTS on SCA Art.29-32, FCA PERG 15.5, PSR 2017 Reg.112-120
Trust Zone: RED

All amounts Decimal (I-01). UTC timestamps. Append-only (I-24).
Blocked jurisdictions (I-02). HITL for irreversible actions (I-27).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, field_validator

# I-02: Blocked jurisdictions
BLOCKED_JURISDICTIONS: set[str] = {
    "RU",
    "BY",
    "IR",
    "KP",
    "CU",
    "MM",
    "AF",
    "VE",
    "SY",
}


# ── Enums ─────────────────────────────────────────────────────────────────────


class ConsentType(StrEnum):
    """PSD2 consent type (AISP/PISP/CBPII)."""

    AISP = "AISP"
    PISP = "PISP"
    CBPII = "CBPII"


class ConsentStatus(StrEnum):
    """Consent lifecycle status."""

    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class TPPType(StrEnum):
    """Third-Party Provider type."""

    AISP = "AISP"
    PISP = "PISP"
    BOTH = "BOTH"


class TPPStatus(StrEnum):
    """TPP registration status."""

    REGISTERED = "REGISTERED"
    SUSPENDED = "SUSPENDED"
    DEREGISTERED = "DEREGISTERED"


class ConsentScope(StrEnum):
    """PSD2 consent data scope."""

    ACCOUNTS = "ACCOUNTS"
    BALANCES = "BALANCES"
    TRANSACTIONS = "TRANSACTIONS"
    PAYMENTS = "PAYMENTS"


# ── Pydantic v2 models ────────────────────────────────────────────────────────


class ConsentGrant(BaseModel):
    """PSD2 consent grant record (pydantic v2, I-01).

    expires_at must be in the future relative to granted_at.
    transaction_limit is Decimal (I-01) or None.
    """

    consent_id: str
    customer_id: str
    tpp_id: str
    consent_type: ConsentType
    scopes: list[ConsentScope]
    granted_at: str
    expires_at: str
    status: ConsentStatus
    transaction_limit: Decimal | None = None  # I-01
    redirect_uri: str

    @field_validator("expires_at")
    @classmethod
    def expires_after_granted(cls, v: str, info: object) -> str:
        """Validate expires_at is after granted_at."""
        data = info.data if hasattr(info, "data") else {}
        granted_at = data.get("granted_at")
        if granted_at and v <= granted_at:
            raise ValueError("expires_at must be after granted_at")
        return v


class TPPRegistration(BaseModel):
    """Third-Party Provider registration (pydantic v2, I-02).

    jurisdiction must NOT be in BLOCKED_JURISDICTIONS (I-02).
    """

    tpp_id: str
    name: str
    eidas_cert_id: str
    tpp_type: TPPType
    status: TPPStatus
    registered_at: str
    jurisdiction: str
    competent_authority: str

    @field_validator("jurisdiction")
    @classmethod
    def jurisdiction_not_blocked(cls, v: str) -> str:
        """I-02: Block sanctioned jurisdictions."""
        if v.upper() in BLOCKED_JURISDICTIONS:
            raise ValueError(
                f"Jurisdiction '{v}' is blocked under I-02 sanctions policy "
                f"(BLOCKED_JURISDICTIONS: {', '.join(sorted(BLOCKED_JURISDICTIONS))})"
            )
        return v


class ConsentAuditEvent(BaseModel):
    """Append-only consent audit event (I-24)."""

    event_id: str
    consent_id: str
    event_type: str
    actor: str
    timestamp: str
    details: str


# ── HITL Proposal (I-27) ──────────────────────────────────────────────────────


@dataclass
class HITLProposal:
    """HITL L4 escalation proposal for irreversible consent operations.

    I-27: AI PROPOSES, human DECIDES.
    """

    action: str
    entity_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


# ── Protocols (Protocol DI) ───────────────────────────────────────────────────


class ConsentStorePort(Protocol):
    """Protocol for consent persistence (append-only, I-24)."""

    def save(self, consent: ConsentGrant) -> None: ...

    def get(self, consent_id: str) -> ConsentGrant | None: ...

    def list_by_customer(self, customer_id: str) -> list[ConsentGrant]: ...

    def list_by_tpp(self, tpp_id: str) -> list[ConsentGrant]: ...


class TPPRegistryPort(Protocol):
    """Protocol for TPP registry."""

    def register(self, tpp: TPPRegistration) -> None: ...

    def get(self, tpp_id: str) -> TPPRegistration | None: ...

    def list_active(self) -> list[TPPRegistration]: ...

    def suspend(self, tpp_id: str) -> HITLProposal: ...


class AuditLogPort(Protocol):
    """Protocol for append-only audit log (I-24)."""

    def append(self, event: ConsentAuditEvent) -> None: ...  # I-24


# ── InMemory stubs ────────────────────────────────────────────────────────────


class InMemoryConsentStore:
    """In-memory consent store (append-only, I-24)."""

    def __init__(self) -> None:
        """Initialise empty consent store."""
        self._data: list[ConsentGrant] = []

    def save(self, consent: ConsentGrant) -> None:
        """Append consent (I-24 — no update/delete)."""
        self._data.append(consent)

    def get(self, consent_id: str) -> ConsentGrant | None:
        """Get latest consent by ID (most recent append)."""
        matches = [c for c in self._data if c.consent_id == consent_id]
        return matches[-1] if matches else None

    def list_by_customer(self, customer_id: str) -> list[ConsentGrant]:
        """List all consents for a customer (all versions)."""
        return [c for c in self._data if c.customer_id == customer_id]

    def list_by_tpp(self, tpp_id: str) -> list[ConsentGrant]:
        """List all consents for a TPP."""
        return [c for c in self._data if c.tpp_id == tpp_id]


class InMemoryTPPRegistry:
    """In-memory TPP registry with 2 seeded TPPs."""

    def __init__(self) -> None:
        """Initialise with Plaid UK and TrueLayer seed data."""
        ts = datetime.now(UTC).isoformat()
        self._data: dict[str, TPPRegistration] = {}
        # Seed: Plaid UK
        plaid = TPPRegistration(
            tpp_id="tpp_plaid_uk",
            name="Plaid UK Limited",
            eidas_cert_id="EIDAS-UK-PLAID-001",
            tpp_type=TPPType.AISP,
            status=TPPStatus.REGISTERED,
            registered_at=ts,
            jurisdiction="GB",
            competent_authority="FCA",
        )
        # Seed: TrueLayer
        truelayer = TPPRegistration(
            tpp_id="tpp_truelayer",
            name="TrueLayer Limited",
            eidas_cert_id="EIDAS-UK-TRUELAYER-001",
            tpp_type=TPPType.BOTH,
            status=TPPStatus.REGISTERED,
            registered_at=ts,
            jurisdiction="GB",
            competent_authority="FCA",
        )
        self._data[plaid.tpp_id] = plaid
        self._data[truelayer.tpp_id] = truelayer

    def register(self, tpp: TPPRegistration) -> None:
        """Register a new TPP."""
        self._data[tpp.tpp_id] = tpp

    def get(self, tpp_id: str) -> TPPRegistration | None:
        """Retrieve a TPP by ID."""
        return self._data.get(tpp_id)

    def list_active(self) -> list[TPPRegistration]:
        """List all REGISTERED TPPs."""
        return [t for t in self._data.values() if t.status == TPPStatus.REGISTERED]

    def suspend(self, tpp_id: str) -> HITLProposal:
        """Return HITL proposal for suspension (I-27)."""
        return HITLProposal(
            action="SUSPEND_TPP",
            entity_id=tpp_id,
            requires_approval_from="COMPLIANCE_OFFICER",
            reason=f"TPP suspension is irreversible action requiring compliance approval (I-27): {tpp_id}",
        )


class InMemoryAuditLog:
    """In-memory append-only audit log (I-24)."""

    def __init__(self) -> None:
        """Initialise empty audit log."""
        self._events: list[ConsentAuditEvent] = []

    def append(self, event: ConsentAuditEvent) -> None:
        """Append audit event (I-24 — no delete)."""
        self._events.append(event)

    def list_all(self) -> list[ConsentAuditEvent]:
        """Return all audit events."""
        return list(self._events)
