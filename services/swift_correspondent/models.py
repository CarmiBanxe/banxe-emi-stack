"""
services/swift_correspondent/models.py
SWIFT & Correspondent Banking — Domain Models
IL-SWF-01 | Sprint 34 | Phase 47

FCA: PSR 2017, SWIFT gpi SRD, MLR 2017 Reg.28, FCA SUP 15.8
Trust Zone: RED
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, field_validator


class SWIFTMessageType(StrEnum):
    """SWIFT message type codes."""

    MT103 = "MT103"  # Customer Credit Transfer
    MT202 = "MT202"  # Financial Institution Transfer
    MT199 = "MT199"  # Free Format (inquiry)
    MT299 = "MT299"  # Free Format (confirm)


class MessageStatus(StrEnum):
    """SWIFT message lifecycle status (I-02 UPPER_SNAKE)."""

    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    SENT = "SENT"
    ACSP = "ACSP"  # Accepted, settlement in process (gpi)
    ACCC = "ACCC"  # Accepted, settlement completed (gpi)
    RJCT = "RJCT"  # Rejected
    HOLD = "HOLD"  # Held pending HITL


class ChargeCode(StrEnum):
    """SWIFT charge code options (field 71A)."""

    SHA = "SHA"  # Shared
    BEN = "BEN"  # Beneficiary bears all charges
    OUR = "OUR"  # Sender bears all charges


class CorrespondentType(StrEnum):
    """Correspondent banking account type."""

    NOSTRO = "nostro"  # Our account at their bank
    VOSTRO = "vostro"  # Their account at our bank


class SWIFTMessage(BaseModel):
    """SWIFT message model (pydantic v2, I-01).

    Represents MT103/MT202/MT199/MT299 SWIFT messages.
    BIC validated to 8 or 11 chars. Remittance capped at 140 chars.
    All amounts as Decimal (I-22).
    """

    message_id: str
    message_type: SWIFTMessageType
    sender_bic: str
    receiver_bic: str
    amount: Decimal  # I-22: Decimal
    currency: str
    value_date: str  # YYYYMMDD
    ordering_customer: str
    beneficiary_customer: str
    remittance_info: str  # field 70, max 140 chars
    charge_code: ChargeCode
    status: MessageStatus = MessageStatus.DRAFT
    uetr: str | None = None  # gpi Unique End-to-End Transaction Reference

    @field_validator("remittance_info")
    @classmethod
    def remittance_max_140(cls, v: str) -> str:
        """Enforce SWIFT field 70 max 140 chars."""
        if len(v) > 140:
            raise ValueError("field 70 remittance_info must be ≤140 chars")
        return v

    @field_validator("sender_bic", "receiver_bic")
    @classmethod
    def validate_bic(cls, v: str) -> str:
        """Validate BIC is 8 or 11 characters."""
        if len(v) not in (8, 11):
            raise ValueError(f"BIC must be 8 or 11 chars, got {len(v)}")
        return v.upper()


class CorrespondentBank(BaseModel):
    """Correspondent bank registration (pydantic v2, I-01).

    Represents a correspondent bank relationship (nostro/vostro).
    FATF risk assessed at registration (I-03).
    """

    bank_id: str
    bic: str
    bank_name: str
    country_code: str  # ISO 3166-1 alpha-2
    correspondent_type: CorrespondentType
    currencies: list[str]
    nostro_account: str | None = None
    vostro_account: str | None = None
    is_active: bool = True
    fatf_risk: str = "low"  # low/medium/high


class NostroPosition(BaseModel):
    """Nostro account reconciliation position (pydantic v2, I-01).

    Append-only snapshot of nostro balance (I-24).
    All amounts as Decimal (I-22). UTC timestamps (I-23).
    """

    position_id: str
    bank_id: str
    currency: str
    our_balance: Decimal  # I-22
    their_balance: Decimal  # I-22
    snapshot_date: str
    mismatch_amount: Decimal = Decimal("0")  # I-22


class GPIStatus(BaseModel):
    """SWIFT gpi transaction status (pydantic v2, I-01).

    Tracks UETR-based gpi status per SWIFT gpi SRD.
    UTC timestamps (I-23).
    """

    uetr: str
    status: MessageStatus
    last_updated: str
    tracker_url: str | None = None
    completion_time: str | None = None


@dataclass
class HITLProposal:
    """HITL L4 escalation proposal (I-11, I-27).

    Human approves critical SWIFT actions.
    Irreversible operations always require L4 approval.
    """

    action: str
    message_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


# ── Protocols (I-01, Protocol DI) ──────────────────────────────────────────


class MessageStore(Protocol):
    """Protocol for SWIFT message persistence."""

    def save(self, msg: SWIFTMessage) -> None: ...

    def get(self, message_id: str) -> SWIFTMessage | None: ...

    def list_by_status(self, status: MessageStatus) -> list[SWIFTMessage]: ...


class CorrespondentStore(Protocol):
    """Protocol for correspondent bank persistence."""

    def save(self, bank: CorrespondentBank) -> None: ...

    def get(self, bank_id: str) -> CorrespondentBank | None: ...

    def find_by_currency(self, currency: str) -> list[CorrespondentBank]: ...


class NostroStore(Protocol):
    """Protocol for nostro position persistence (append-only, I-24)."""

    def append(self, position: NostroPosition) -> None: ...  # I-24

    def get_latest(self, bank_id: str, currency: str) -> NostroPosition | None: ...


# ── InMemory stubs ──────────────────────────────────────────────────────────


class InMemoryMessageStore:
    """In-memory SWIFT message store for testing."""

    def __init__(self) -> None:
        """Initialise empty message store."""
        self._data: dict[str, SWIFTMessage] = {}

    def save(self, msg: SWIFTMessage) -> None:
        """Save or update a SWIFT message."""
        self._data[msg.message_id] = msg

    def get(self, message_id: str) -> SWIFTMessage | None:
        """Retrieve a SWIFT message by ID."""
        return self._data.get(message_id)

    def list_by_status(self, status: MessageStatus) -> list[SWIFTMessage]:
        """List all messages with a given status."""
        return [m for m in self._data.values() if m.status == status]


class InMemoryCorrespondentStore:
    """In-memory correspondent bank store with 3 seeded banks."""

    def __init__(self) -> None:
        """Initialise with seeded correspondent banks (Deutsche/Barclays/JPMorgan)."""
        self._data: dict[str, CorrespondentBank] = {
            "cb_001": CorrespondentBank(
                bank_id="cb_001",
                bic="DEUTDEDB",
                bank_name="Deutsche Bank",
                country_code="DE",
                correspondent_type=CorrespondentType.NOSTRO,
                currencies=["EUR", "USD"],
                nostro_account="DE91100000000123456789",
            ),
            "cb_002": CorrespondentBank(
                bank_id="cb_002",
                bic="BARCGB22",
                bank_name="Barclays",
                country_code="GB",
                correspondent_type=CorrespondentType.NOSTRO,
                currencies=["GBP", "USD"],
                nostro_account="GB29NWBK60161331926819",
            ),
            "cb_003": CorrespondentBank(
                bank_id="cb_003",
                bic="CHASUS33",
                bank_name="JPMorgan Chase",
                country_code="US",
                correspondent_type=CorrespondentType.NOSTRO,
                currencies=["USD"],
                nostro_account="US33CHAS0000000123456",
            ),
        }

    def save(self, bank: CorrespondentBank) -> None:
        """Save or update a correspondent bank."""
        self._data[bank.bank_id] = bank

    def get(self, bank_id: str) -> CorrespondentBank | None:
        """Retrieve a correspondent bank by ID."""
        return self._data.get(bank_id)

    def find_by_currency(self, currency: str) -> list[CorrespondentBank]:
        """Find active correspondent banks supporting a currency."""
        return [b for b in self._data.values() if currency in b.currencies and b.is_active]


class InMemoryNostroStore:
    """In-memory nostro position store (append-only, I-24)."""

    def __init__(self) -> None:
        """Initialise empty append-only log."""
        self._log: list[NostroPosition] = []

    def append(self, position: NostroPosition) -> None:  # I-24
        """Append nostro snapshot (never update/delete)."""
        self._log.append(position)

    def get_latest(self, bank_id: str, currency: str) -> NostroPosition | None:
        """Get most recent position for a bank/currency pair."""
        matches = [p for p in self._log if p.bank_id == bank_id and p.currency == currency]
        return matches[-1] if matches else None
