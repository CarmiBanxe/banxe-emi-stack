"""
services/beneficiary_management/models.py — Domain models for Beneficiary & Payee Management
IL-BPM-01 | Phase 34 | banxe-emi-stack
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol, runtime_checkable

# I-02 hard-blocked jurisdictions
BLOCKED_JURISDICTIONS: frozenset[str] = frozenset(
    {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}
)

# I-03 FATF greylist (subset — expand as needed)
FATF_GREYLIST: frozenset[str] = frozenset(
    {"PK", "TR", "AE", "JO", "LK", "SN", "SD", "SS", "NG", "YE", "ML", "BF", "HT"}
)


class BeneficiaryType(str, Enum):
    INDIVIDUAL = "INDIVIDUAL"
    BUSINESS = "BUSINESS"
    JOINT = "JOINT"


class BeneficiaryStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DEACTIVATED = "DEACTIVATED"


class ScreeningResult(str, Enum):
    NO_MATCH = "NO_MATCH"
    PARTIAL_MATCH = "PARTIAL_MATCH"
    MATCH = "MATCH"


class PaymentRail(str, Enum):
    FPS = "FPS"
    BACS = "BACS"
    CHAPS = "CHAPS"
    SEPA = "SEPA"
    SWIFT = "SWIFT"


@dataclasses.dataclass(frozen=True)
class Beneficiary:
    beneficiary_id: str
    customer_id: str
    beneficiary_type: BeneficiaryType
    name: str
    account_number: str
    sort_code: str
    iban: str
    bic: str
    currency: str
    country_code: str
    status: BeneficiaryStatus
    created_at: datetime
    trusted: bool = False
    screening_result: ScreeningResult | None = None
    screening_at: datetime | None = None


@dataclasses.dataclass(frozen=True)
class ScreeningRecord:
    record_id: str
    beneficiary_id: str
    result: ScreeningResult
    checked_at: datetime
    watchman_ref: str = ""
    details: str = ""


@dataclasses.dataclass(frozen=True)
class CoPResult:
    result: str  # MATCH | CLOSE_MATCH | NO_MATCH
    beneficiary_id: str
    expected_name: str
    matched_name: str
    checked_at: datetime


@dataclasses.dataclass(frozen=True)
class TrustedBeneficiary:
    trust_id: str
    beneficiary_id: str
    customer_id: str
    daily_limit: Decimal
    approved_by: str
    approved_at: datetime
    is_active: bool = True


@dataclasses.dataclass(frozen=True)
class PaymentRailSelection:
    rail: PaymentRail
    estimated_settlement: str
    fee_indicator: str
    currency: str
    max_amount: Decimal | None = None


@runtime_checkable
class BeneficiaryPort(Protocol):
    def save(self, beneficiary: Beneficiary) -> None: ...
    def get(self, beneficiary_id: str) -> Beneficiary | None: ...
    def update(self, beneficiary: Beneficiary) -> None: ...
    def list_by_customer(self, customer_id: str) -> list[Beneficiary]: ...


@runtime_checkable
class ScreeningPort(Protocol):
    def save(self, record: ScreeningRecord) -> None: ...
    def list_by_beneficiary(self, beneficiary_id: str) -> list[ScreeningRecord]: ...


@runtime_checkable
class TrustedBeneficiaryPort(Protocol):
    def save(self, trust: TrustedBeneficiary) -> None: ...
    def get_by_beneficiary(self, beneficiary_id: str) -> TrustedBeneficiary | None: ...
    def update(self, trust: TrustedBeneficiary) -> None: ...


@runtime_checkable
class CoPPort(Protocol):
    def save(self, result: CoPResult) -> None: ...
    def list_by_beneficiary(self, beneficiary_id: str) -> list[CoPResult]: ...


class InMemoryBeneficiaryStore:
    def __init__(self) -> None:
        self._data: dict[str, Beneficiary] = {}

    def save(self, beneficiary: Beneficiary) -> None:
        self._data[beneficiary.beneficiary_id] = beneficiary

    def get(self, beneficiary_id: str) -> Beneficiary | None:
        return self._data.get(beneficiary_id)

    def update(self, beneficiary: Beneficiary) -> None:
        self._data[beneficiary.beneficiary_id] = beneficiary

    def list_by_customer(self, customer_id: str) -> list[Beneficiary]:
        return [b for b in self._data.values() if b.customer_id == customer_id]


class InMemoryScreeningStore:
    """Append-only screening history (I-24)."""

    def __init__(self) -> None:
        self._records: list[ScreeningRecord] = []

    def save(self, record: ScreeningRecord) -> None:
        self._records.append(record)

    def list_by_beneficiary(self, beneficiary_id: str) -> list[ScreeningRecord]:
        return [r for r in self._records if r.beneficiary_id == beneficiary_id]


class InMemoryTrustedBeneficiaryStore:
    def __init__(self) -> None:
        self._data: dict[str, TrustedBeneficiary] = {}

    def save(self, trust: TrustedBeneficiary) -> None:
        self._data[trust.beneficiary_id] = trust

    def get_by_beneficiary(self, beneficiary_id: str) -> TrustedBeneficiary | None:
        return self._data.get(beneficiary_id)

    def update(self, trust: TrustedBeneficiary) -> None:
        self._data[trust.beneficiary_id] = trust


class InMemoryCoPStore:
    """Append-only CoP result store (I-24)."""

    def __init__(self) -> None:
        self._records: list[CoPResult] = []

    def save(self, result: CoPResult) -> None:
        self._records.append(result)

    def list_by_beneficiary(self, beneficiary_id: str) -> list[CoPResult]:
        return [r for r in self._records if r.beneficiary_id == beneficiary_id]
