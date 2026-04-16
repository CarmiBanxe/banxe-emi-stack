"""
services/card_issuing/models.py
IL-CIM-01 | Phase 19

Domain models, enums, protocols, and InMemory stubs for card issuing.
PIN NEVER stored plain — only hash (I-12).
Amounts always Decimal (I-01). API layer uses strings (I-05).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol, runtime_checkable

# ── Enums ─────────────────────────────────────────────────────────────────────


class CardStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    BLOCKED = "BLOCKED"
    EXPIRED = "EXPIRED"
    REPLACED = "REPLACED"


class CardType(str, Enum):
    VIRTUAL = "VIRTUAL"
    PHYSICAL = "PHYSICAL"


class CardNetwork(str, Enum):
    MASTERCARD = "MASTERCARD"
    VISA = "VISA"


class SpendPeriod(str, Enum):
    DAILY = "DAILY"
    MONTHLY = "MONTHLY"
    PER_TRANSACTION = "PER_TRANSACTION"


class AuthorisationResult(str, Enum):
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    REFERRED = "REFERRED"


class TransactionType(str, Enum):
    PURCHASE = "PURCHASE"
    REFUND = "REFUND"
    CASH_ADVANCE = "CASH_ADVANCE"
    FEE = "FEE"


# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BINRange:
    id: str
    network: CardNetwork
    bin_prefix: str
    country: str
    currency: str
    issuer: str


@dataclass(frozen=True)
class Card:
    id: str
    entity_id: str
    card_type: CardType
    network: CardNetwork
    bin_range_id: str
    last_four: str
    expiry_month: int
    expiry_year: int
    status: CardStatus
    created_at: datetime
    activated_at: datetime | None
    pin_hash: str | None
    name_on_card: str


@dataclass(frozen=True)
class SpendLimit:
    card_id: str
    period: SpendPeriod
    limit_amount: Decimal
    currency: str
    blocked_mccs: list[str]
    geo_restrictions: list[str]


@dataclass(frozen=True)
class CardAuthorisation:
    id: str
    card_id: str
    amount: Decimal
    currency: str
    merchant_name: str
    merchant_mcc: str
    merchant_country: str
    result: AuthorisationResult
    decline_reason: str | None
    authorised_at: datetime
    transaction_type: TransactionType


@dataclass(frozen=True)
class CardTransaction:
    id: str
    card_id: str
    authorisation_id: str
    amount: Decimal
    currency: str
    merchant_name: str
    merchant_mcc: str
    posted_at: datetime
    transaction_type: TransactionType
    settled: bool


@dataclass(frozen=True)
class CardEventEntry:
    id: str
    card_id: str
    event_type: str
    entity_id: str
    actor: str
    details: dict
    created_at: datetime


# ── Protocols ─────────────────────────────────────────────────────────────────


@runtime_checkable
class CardStorePort(Protocol):
    async def save(self, card: Card) -> None: ...
    async def get(self, card_id: str) -> Card | None: ...
    async def list_by_entity(self, entity_id: str) -> list[Card]: ...


@runtime_checkable
class SpendLimitStorePort(Protocol):
    async def save(self, limit: SpendLimit) -> None: ...
    async def get(self, card_id: str) -> SpendLimit | None: ...


@runtime_checkable
class TransactionStorePort(Protocol):
    async def save_auth(self, auth: CardAuthorisation) -> None: ...
    async def save_txn(self, txn: CardTransaction) -> None: ...
    async def list_auths(self, card_id: str) -> list[CardAuthorisation]: ...
    async def list_txns(self, card_id: str) -> list[CardTransaction]: ...
    async def get_auth(self, auth_id: str) -> CardAuthorisation | None: ...


@runtime_checkable
class CardAuditPort(Protocol):
    async def log(
        self,
        event_type: str,
        card_id: str,
        entity_id: str,
        actor: str,
        details: dict,
    ) -> None: ...

    async def list_events(self, card_id: str | None = None) -> list[dict]: ...


# ── InMemory stubs ────────────────────────────────────────────────────────────


class InMemoryCardStore:
    """Dict-backed InMemory stub for CardStorePort."""

    def __init__(self) -> None:
        self._cards: dict[str, Card] = {}

    async def save(self, card: Card) -> None:
        self._cards[card.id] = card

    async def get(self, card_id: str) -> Card | None:
        return self._cards.get(card_id)

    async def list_by_entity(self, entity_id: str) -> list[Card]:
        return [c for c in self._cards.values() if c.entity_id == entity_id]


class InMemorySpendLimitStore:
    """Dict-backed InMemory stub for SpendLimitStorePort."""

    def __init__(self) -> None:
        self._limits: dict[str, SpendLimit] = {}

    async def save(self, limit: SpendLimit) -> None:
        self._limits[limit.card_id] = limit

    async def get(self, card_id: str) -> SpendLimit | None:
        return self._limits.get(card_id)


class InMemoryTransactionStore:
    """List-backed InMemory stub for TransactionStorePort."""

    def __init__(self) -> None:
        self._auths: list[CardAuthorisation] = []
        self._txns: list[CardTransaction] = []

    async def save_auth(self, auth: CardAuthorisation) -> None:
        self._auths.append(auth)

    async def save_txn(self, txn: CardTransaction) -> None:
        self._txns.append(txn)

    async def list_auths(self, card_id: str) -> list[CardAuthorisation]:
        return [a for a in self._auths if a.card_id == card_id]

    async def list_txns(self, card_id: str) -> list[CardTransaction]:
        return [t for t in self._txns if t.card_id == card_id]

    async def get_auth(self, auth_id: str) -> CardAuthorisation | None:
        for auth in self._auths:
            if auth.id == auth_id:
                return auth
        return None


class InMemoryCardAudit:
    """List-backed InMemory stub for CardAuditPort."""

    def __init__(self) -> None:
        self._events: list[dict] = []

    async def log(
        self,
        event_type: str,
        card_id: str,
        entity_id: str,
        actor: str,
        details: dict,
    ) -> None:
        self._events.append(
            {
                "event_type": event_type,
                "card_id": card_id,
                "entity_id": entity_id,
                "actor": actor,
                "details": details,
                "created_at": datetime.now(UTC).isoformat(),
            }
        )

    async def list_events(self, card_id: str | None = None) -> list[dict]:
        if card_id is None:
            return list(self._events)
        return [e for e in self._events if e.get("card_id") == card_id]


# ── BIN ranges ────────────────────────────────────────────────────────────────

_SAMPLE_BINS: list[BINRange] = [
    BINRange(
        id="bin-mc-001",
        network=CardNetwork.MASTERCARD,
        bin_prefix="531604",
        country="GB",
        currency="GBP",
        issuer="Banxe EMI Ltd",
    ),
    BINRange(
        id="bin-visa-001",
        network=CardNetwork.VISA,
        bin_prefix="427316",
        country="GB",
        currency="GBP",
        issuer="Banxe EMI Ltd",
    ),
]
