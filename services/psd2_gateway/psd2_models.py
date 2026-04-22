"""PSD2 Gateway models — adorsys XS2A AISP/PISP.

IL-PSD2GW-01 | Phase 52B | Sprint 37
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

BLOCKED_JURISDICTIONS = {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}


def _iban_country(iban: str) -> str:
    """Extract 2-letter country code from IBAN (first 2 chars)."""
    return iban[:2].upper() if len(iban) >= 2 else ""


@dataclass(frozen=True)
class ConsentRequest:
    iban: str
    access_type: str  # "allAccounts" | "allAccountsWithOwnerName"
    valid_until: str  # ISO date YYYY-MM-DD
    recurring_indicator: bool = True
    frequency_per_day: int = 4


@dataclass(frozen=True)
class ConsentResponse:
    consent_id: str
    status: str  # "received" | "valid" | "expired" | "terminatedByTpp" | "revokedByPsu"
    valid_until: str
    iban: str
    created_at: str  # UTC ISO


@dataclass(frozen=True)
class AccountInfo:
    account_id: str
    iban: str
    currency: str
    account_type: str
    name: str | None


@dataclass(frozen=True)
class Transaction:
    transaction_id: str
    amount: Decimal  # I-01
    currency: str
    creditor_name: str | None
    debtor_name: str | None
    booking_date: str  # ISO date
    value_date: str  # ISO date
    reference: str | None


@dataclass(frozen=True)
class BalanceResponse:
    account_id: str
    iban: str
    currency: str
    balance_amount: Decimal  # I-01
    balance_type: str  # "closingBooked" | "expected"
    last_change_date_time: str  # UTC ISO


class ConsentStorePort(Protocol):
    def append(self, consent: ConsentResponse) -> None: ...

    def get(self, consent_id: str) -> ConsentResponse | None: ...

    def list_active(self) -> list[ConsentResponse]: ...


class TransactionStorePort(Protocol):
    def append(self, txn: Transaction) -> None: ...

    def list_by_account(self, account_id: str) -> list[Transaction]: ...


class InMemoryConsentStore:
    def __init__(self) -> None:
        self._consents: list[ConsentResponse] = []

    def append(self, c: ConsentResponse) -> None:
        self._consents.append(c)

    def get(self, cid: str) -> ConsentResponse | None:
        return next((c for c in self._consents if c.consent_id == cid), None)

    def list_active(self) -> list[ConsentResponse]:
        return [c for c in self._consents if c.status == "valid"]


class InMemoryTransactionStore:
    def __init__(self) -> None:
        self._txns: list[Transaction] = []

    def append(self, t: Transaction) -> None:
        self._txns.append(t)

    def list_by_account(self, account_id: str) -> list[Transaction]:
        return list(self._txns)  # stub — returns all
