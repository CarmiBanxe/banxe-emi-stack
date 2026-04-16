"""
services/multi_currency/models.py — Domain models, enums, protocols, and InMemory stubs.

Phase 22 | IL-MCL-01 | banxe-emi-stack

Invariants:
  - I-01: All monetary amounts are Decimal — never float.
  - I-24: Audit trail is append-only.
  - max_currencies = 10 per account (hard limit).
  - Nostro tolerance = Decimal("1.00").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol, runtime_checkable

# ── Seed data ─────────────────────────────────────────────────────────────────

_SUPPORTED_CURRENCIES: list[str] = [
    "GBP",
    "EUR",
    "USD",
    "CHF",
    "PLN",
    "CZK",
    "SEK",
    "NOK",
    "DKK",
    "HUF",
]

# ── Enums ─────────────────────────────────────────────────────────────────────


class ReconciliationStatus(str, Enum):
    MATCHED = "MATCHED"
    DISCREPANCY = "DISCREPANCY"
    PENDING = "PENDING"


class ConversionStatus(str, Enum):
    COMPLETED = "COMPLETED"
    PENDING = "PENDING"
    FAILED = "FAILED"


class NostroType(str, Enum):
    NOSTRO = "NOSTRO"
    VOSTRO = "VOSTRO"
    LORO = "LORO"


class RoutingStrategy(str, Enum):
    CHEAPEST = "CHEAPEST"
    FASTEST = "FASTEST"
    DIRECT = "DIRECT"


# ── Domain dataclasses ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CurrencyBalance:
    """Balance held in a single currency."""

    currency: str
    amount: Decimal
    available: Decimal
    reserved: Decimal


@dataclass(frozen=True)
class MultiCurrencyAccount:
    """Account holding balances in multiple currencies (max 10)."""

    account_id: str
    entity_id: str
    base_currency: str
    balances: tuple[CurrencyBalance, ...]
    created_at: datetime
    max_currencies: int = 10


@dataclass(frozen=True)
class LedgerEntry:
    """Immutable ledger entry — append-only (I-24). direction: DEBIT or CREDIT."""

    entry_id: str
    account_id: str
    currency: str
    amount: Decimal
    direction: str  # "DEBIT" or "CREDIT"
    description: str
    created_at: datetime


@dataclass(frozen=True)
class ConversionRecord:
    """Record of a currency conversion with fee (0.2%) and status."""

    conversion_id: str
    account_id: str
    from_currency: str
    to_currency: str
    from_amount: Decimal
    to_amount: Decimal
    rate: Decimal
    fee: Decimal
    status: ConversionStatus
    created_at: datetime


@dataclass(frozen=True)
class NostroAccount:
    """Nostro/vostro/loro correspondent banking account."""

    account_id: str
    bank_name: str
    currency: str
    our_balance: Decimal
    their_balance: Decimal
    account_type: NostroType
    last_reconciled: datetime | None = None


@dataclass(frozen=True)
class ReconciliationResult:
    """Result of nostro reconciliation: variance and MATCHED/DISCREPANCY status."""

    nostro_id: str
    our_balance: Decimal
    their_balance: Decimal
    variance: Decimal
    status: ReconciliationStatus
    reconciled_at: datetime


@dataclass(frozen=True)
class MCEventEntry:
    """Append-only audit event for multi-currency operations (I-24)."""

    event_id: str
    account_id: str
    event_type: str
    currency: str
    amount: Decimal
    created_at: datetime


# ── Protocols ─────────────────────────────────────────────────────────────────


@runtime_checkable
class AccountStorePort(Protocol):
    async def save(self, account: MultiCurrencyAccount) -> None: ...
    async def get(self, account_id: str) -> MultiCurrencyAccount | None: ...
    async def list_by_entity(self, entity_id: str) -> list[MultiCurrencyAccount]: ...


@runtime_checkable
class LedgerEntryPort(Protocol):
    async def append(self, entry: LedgerEntry) -> None: ...
    async def list_entries(
        self, account_id: str, currency: str | None = None
    ) -> list[LedgerEntry]: ...


@runtime_checkable
class ConversionStorePort(Protocol):
    async def save(self, record: ConversionRecord) -> None: ...
    async def get(self, conversion_id: str) -> ConversionRecord | None: ...
    async def list_by_account(self, account_id: str) -> list[ConversionRecord]: ...


@runtime_checkable
class NostroStorePort(Protocol):
    async def save(self, account: NostroAccount) -> None: ...
    async def get(self, account_id: str) -> NostroAccount | None: ...
    async def list_all(self) -> list[NostroAccount]: ...


@runtime_checkable
class MCAuditPort(Protocol):
    async def log(self, entry: MCEventEntry) -> None: ...
    async def list_events(self, account_id: str | None = None) -> list[MCEventEntry]: ...


# ── InMemory stubs ────────────────────────────────────────────────────────────


class InMemoryAccountStore:
    """Dict-backed InMemory stub for AccountStorePort."""

    def __init__(self) -> None:
        self._accounts: dict[str, MultiCurrencyAccount] = {}

    async def save(self, account: MultiCurrencyAccount) -> None:
        self._accounts[account.account_id] = account

    async def get(self, account_id: str) -> MultiCurrencyAccount | None:
        return self._accounts.get(account_id)

    async def list_by_entity(self, entity_id: str) -> list[MultiCurrencyAccount]:
        return [a for a in self._accounts.values() if a.entity_id == entity_id]


class InMemoryLedgerEntryStore:
    """List-backed InMemory stub for LedgerEntryPort (append-only, I-24)."""

    def __init__(self) -> None:
        self._entries: list[LedgerEntry] = []

    async def append(self, entry: LedgerEntry) -> None:
        self._entries.append(entry)

    async def list_entries(self, account_id: str, currency: str | None = None) -> list[LedgerEntry]:
        entries = [e for e in self._entries if e.account_id == account_id]
        if currency is not None:
            entries = [e for e in entries if e.currency == currency]
        return entries


class InMemoryConversionStore:
    """Dict-backed InMemory stub for ConversionStorePort."""

    def __init__(self) -> None:
        self._records: dict[str, ConversionRecord] = {}

    async def save(self, record: ConversionRecord) -> None:
        self._records[record.conversion_id] = record

    async def get(self, conversion_id: str) -> ConversionRecord | None:
        return self._records.get(conversion_id)

    async def list_by_account(self, account_id: str) -> list[ConversionRecord]:
        return [r for r in self._records.values() if r.account_id == account_id]


class InMemoryNostroStore:
    """Dict-backed InMemory stub for NostroStorePort — seeded with 2 nostro accounts."""

    def __init__(self) -> None:
        self._accounts: dict[str, NostroAccount] = {}
        for acct in _NOSTRO_ACCOUNTS:
            self._accounts[acct.account_id] = acct

    async def save(self, account: NostroAccount) -> None:
        self._accounts[account.account_id] = account

    async def get(self, account_id: str) -> NostroAccount | None:
        return self._accounts.get(account_id)

    async def list_all(self) -> list[NostroAccount]:
        return list(self._accounts.values())


class InMemoryMCAudit:
    """List-backed InMemory stub for MCAuditPort (append-only, I-24)."""

    def __init__(self) -> None:
        self._events: list[MCEventEntry] = []

    async def log(self, entry: MCEventEntry) -> None:
        self._events.append(entry)

    async def list_events(self, account_id: str | None = None) -> list[MCEventEntry]:
        if account_id is None:
            return list(self._events)
        return [e for e in self._events if e.account_id == account_id]


# ── Seeded nostro accounts ────────────────────────────────────────────────────

_NOSTRO_ACCOUNTS: list[NostroAccount] = [
    NostroAccount(
        account_id="nostro-gbp-001",
        bank_name="Barclays",
        currency="GBP",
        our_balance=Decimal("5_000_000"),
        their_balance=Decimal("5_000_000"),
        account_type=NostroType.NOSTRO,
        last_reconciled=None,
    ),
    NostroAccount(
        account_id="nostro-eur-001",
        bank_name="BNP Paribas",
        currency="EUR",
        our_balance=Decimal("3_000_000"),
        their_balance=Decimal("3_000_000"),
        account_type=NostroType.NOSTRO,
        last_reconciled=None,
    ),
]
