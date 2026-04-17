"""
services/lending/models.py — Lending & Credit Engine domain models
IL-LCE-01 | Phase 25 | banxe-emi-stack

Domain models, enums, protocols, and InMemory stubs for the lending engine.
All monetary amounts use Decimal (I-01). Frozen dataclasses throughout.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol

# ── Enums ──────────────────────────────────────────────────────────────────


class LoanStatus(str, Enum):
    """Lifecycle states for a loan application."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    DISBURSED = "DISBURSED"
    ACTIVE = "ACTIVE"
    IN_ARREARS = "IN_ARREARS"
    DEFAULTED = "DEFAULTED"
    CLOSED = "CLOSED"


class LoanProductType(str, Enum):
    """Types of loan products available."""

    OVERDRAFT = "OVERDRAFT"
    CREDIT_LINE = "CREDIT_LINE"
    MICRO_LOAN = "MICRO_LOAN"
    PERSONAL_LOAN = "PERSONAL_LOAN"


class ArrearStage(str, Enum):
    """IFRS 9-aligned arrear staging by days overdue."""

    CURRENT = "CURRENT"
    DAYS_1_30 = "DAYS_1_30"
    DAYS_31_60 = "DAYS_31_60"
    DAYS_61_90 = "DAYS_61_90"
    DEFAULT_90_PLUS = "DEFAULT_90_PLUS"


class IFRSStage(str, Enum):
    """IFRS 9 impairment stages for ECL provisioning."""

    STAGE_1 = "STAGE_1"
    STAGE_2 = "STAGE_2"
    STAGE_3 = "STAGE_3"


class RepaymentType(str, Enum):
    """Schedule calculation method."""

    ANNUITY = "ANNUITY"
    LINEAR = "LINEAR"


class DecisionOutcome(str, Enum):
    """Outcome of a credit decision."""

    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    REFERRED = "REFERRED"


# ── Frozen dataclasses ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class LoanProduct:
    """A configured loan product available in the catalogue."""

    product_id: str
    name: str
    product_type: LoanProductType
    max_amount: Decimal
    interest_rate: Decimal
    max_term_months: int
    min_credit_score: Decimal
    created_at: datetime


@dataclass(frozen=True)
class LoanApplication:
    """A customer's loan application at a given point in time."""

    application_id: str
    customer_id: str
    product_id: str
    requested_amount: Decimal
    requested_term_months: int
    status: LoanStatus
    applied_at: datetime
    decided_at: datetime | None = None
    decision_note: str = ""


@dataclass(frozen=True)
class CreditDecision:
    """Outcome record from the credit underwriting process."""

    decision_id: str
    application_id: str
    outcome: DecisionOutcome
    credit_score: Decimal
    approved_amount: Decimal | None
    approved_rate: Decimal | None
    decided_at: datetime
    decided_by: str


@dataclass(frozen=True)
class RepaymentSchedule:
    """Full amortisation schedule for an approved loan."""

    schedule_id: str
    application_id: str
    total_amount: Decimal
    monthly_payment: Decimal
    repayment_type: RepaymentType
    installments: list[dict]  # [{"month": int, "payment": str, ...}]
    created_at: datetime


@dataclass(frozen=True)
class CreditScore:
    """Customer creditworthiness snapshot."""

    score_id: str
    customer_id: str
    score: Decimal
    income_factor: Decimal
    history_factor: Decimal
    aml_risk_factor: Decimal
    computed_at: datetime


@dataclass(frozen=True)
class ArrearsRecord:
    """A single arrears observation for an application."""

    record_id: str
    application_id: str
    customer_id: str
    stage: ArrearStage
    days_overdue: int
    outstanding_amount: Decimal
    recorded_at: datetime


@dataclass(frozen=True)
class ProvisionRecord:
    """IFRS 9 ECL provision calculation record."""

    record_id: str
    application_id: str
    ifrs_stage: IFRSStage
    ecl_amount: Decimal
    probability_of_default: Decimal
    exposure_at_default: Decimal
    computed_at: datetime


# ── Protocols ──────────────────────────────────────────────────────────────


class LoanProductStorePort(Protocol):
    """Port for loan product catalogue persistence."""

    def get(self, product_id: str) -> LoanProduct | None: ...

    def list_products(self) -> list[LoanProduct]: ...


class LoanApplicationStorePort(Protocol):
    """Port for loan application persistence."""

    def save(self, app: LoanApplication) -> None: ...

    def get(self, app_id: str) -> LoanApplication | None: ...

    def list_by_customer(self, customer_id: str) -> list[LoanApplication]: ...


class CreditDecisionStorePort(Protocol):
    """Port for credit decision persistence."""

    def save(self, d: CreditDecision) -> None: ...

    def get(self, d_id: str) -> CreditDecision | None: ...


class ArrearsStorePort(Protocol):
    """Port for arrears record persistence."""

    def save(self, r: ArrearsRecord) -> None: ...

    def list_by_application(self, app_id: str) -> list[ArrearsRecord]: ...


class ProvisionStorePort(Protocol):
    """Port for provision record persistence."""

    def save(self, p: ProvisionRecord) -> None: ...

    def list_by_application(self, app_id: str) -> list[ProvisionRecord]: ...


# ── InMemory stubs ─────────────────────────────────────────────────────────


class InMemoryLoanProductStore:
    """InMemory stub for LoanProductStorePort. Seeded with 3 products."""

    def __init__(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=UTC)
        self._store: dict[str, LoanProduct] = {
            "product-001": LoanProduct(
                product_id="product-001",
                name="Micro Loan",
                product_type=LoanProductType.MICRO_LOAN,
                max_amount=Decimal("2000"),
                interest_rate=Decimal("0.0499"),
                max_term_months=12,
                min_credit_score=Decimal("500"),
                created_at=now,
            ),
            "product-002": LoanProduct(
                product_id="product-002",
                name="Personal Loan",
                product_type=LoanProductType.PERSONAL_LOAN,
                max_amount=Decimal("15000"),
                interest_rate=Decimal("0.0899"),
                max_term_months=60,
                min_credit_score=Decimal("600"),
                created_at=now,
            ),
            "product-003": LoanProduct(
                product_id="product-003",
                name="Credit Line",
                product_type=LoanProductType.CREDIT_LINE,
                max_amount=Decimal("5000"),
                interest_rate=Decimal("0.1499"),
                max_term_months=24,
                min_credit_score=Decimal("550"),
                created_at=now,
            ),
        }

    def get(self, product_id: str) -> LoanProduct | None:
        return self._store.get(product_id)

    def list_products(self) -> list[LoanProduct]:
        return list(self._store.values())


class InMemoryLoanApplicationStore:
    """InMemory stub for LoanApplicationStorePort."""

    def __init__(self) -> None:
        self._store: dict[str, LoanApplication] = {}

    def save(self, app: LoanApplication) -> None:
        self._store[app.application_id] = app

    def get(self, app_id: str) -> LoanApplication | None:
        return self._store.get(app_id)

    def list_by_customer(self, customer_id: str) -> list[LoanApplication]:
        return [a for a in self._store.values() if a.customer_id == customer_id]


class InMemoryCreditDecisionStore:
    """InMemory stub for CreditDecisionStorePort."""

    def __init__(self) -> None:
        self._store: dict[str, CreditDecision] = {}

    def save(self, d: CreditDecision) -> None:
        self._store[d.decision_id] = d

    def get(self, d_id: str) -> CreditDecision | None:
        return self._store.get(d_id)


class InMemoryArrearsStore:
    """InMemory stub for ArrearsStorePort."""

    def __init__(self) -> None:
        self._records: list[ArrearsRecord] = []

    def save(self, r: ArrearsRecord) -> None:
        self._records.append(r)

    def list_by_application(self, app_id: str) -> list[ArrearsRecord]:
        return [r for r in self._records if r.application_id == app_id]


class InMemoryProvisionStore:
    """InMemory stub for ProvisionStorePort."""

    def __init__(self) -> None:
        self._records: list[ProvisionRecord] = []

    def save(self, p: ProvisionRecord) -> None:
        self._records.append(p)

    def list_by_application(self, app_id: str) -> list[ProvisionRecord]:
        return [r for r in self._records if r.application_id == app_id]
