"""
tests/test_lending/test_models.py — Unit tests for lending domain models
IL-LCE-01 | Phase 25

20 tests covering dataclass creation, frozen enforcement, enum values,
InMemory store CRUD, and seeded product catalogue.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.lending.models import (
    ArrearStage,
    CreditDecision,
    DecisionOutcome,
    IFRSStage,
    InMemoryLoanApplicationStore,
    InMemoryLoanProductStore,
    LoanApplication,
    LoanProduct,
    LoanProductType,
    LoanStatus,
    ProvisionRecord,
    RepaymentType,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


# ── LoanProduct dataclass ──────────────────────────────────────────────────


def test_loan_product_creation() -> None:
    p = LoanProduct(
        product_id="p-1",
        name="Test Loan",
        product_type=LoanProductType.MICRO_LOAN,
        max_amount=Decimal("500"),
        interest_rate=Decimal("0.05"),
        max_term_months=6,
        min_credit_score=Decimal("400"),
        created_at=NOW,
    )
    assert p.product_id == "p-1"
    assert p.max_amount == Decimal("500")


def test_loan_product_is_frozen() -> None:
    p = LoanProduct(
        product_id="p-1",
        name="Test",
        product_type=LoanProductType.MICRO_LOAN,
        max_amount=Decimal("500"),
        interest_rate=Decimal("0.05"),
        max_term_months=6,
        min_credit_score=Decimal("400"),
        created_at=NOW,
    )
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        p.max_amount = Decimal("999")  # type: ignore[misc]


def test_loan_product_type_enum_values() -> None:
    assert LoanProductType.MICRO_LOAN.value == "MICRO_LOAN"
    assert LoanProductType.PERSONAL_LOAN.value == "PERSONAL_LOAN"
    assert LoanProductType.CREDIT_LINE.value == "CREDIT_LINE"
    assert LoanProductType.OVERDRAFT.value == "OVERDRAFT"


def test_loan_status_enum_values() -> None:
    expected = {
        "PENDING",
        "APPROVED",
        "DECLINED",
        "DISBURSED",
        "ACTIVE",
        "IN_ARREARS",
        "DEFAULTED",
        "CLOSED",
    }
    assert {s.value for s in LoanStatus} == expected


def test_loan_application_defaults() -> None:
    app = LoanApplication(
        application_id="app-1",
        customer_id="cust-1",
        product_id="p-1",
        requested_amount=Decimal("1000"),
        requested_term_months=12,
        status=LoanStatus.PENDING,
        applied_at=NOW,
    )
    assert app.decided_at is None
    assert app.decision_note == ""


def test_loan_application_is_frozen() -> None:
    app = LoanApplication(
        application_id="app-1",
        customer_id="cust-1",
        product_id="p-1",
        requested_amount=Decimal("1000"),
        requested_term_months=12,
        status=LoanStatus.PENDING,
        applied_at=NOW,
    )
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        app.status = LoanStatus.APPROVED  # type: ignore[misc]


def test_credit_decision_creation() -> None:
    d = CreditDecision(
        decision_id="d-1",
        application_id="app-1",
        outcome=DecisionOutcome.APPROVED,
        credit_score=Decimal("750"),
        approved_amount=Decimal("1000"),
        approved_rate=Decimal("0.05"),
        decided_at=NOW,
        decided_by="system",
    )
    assert d.outcome == DecisionOutcome.APPROVED
    assert isinstance(d.approved_amount, Decimal)


def test_credit_decision_declined_nullable_amounts() -> None:
    d = CreditDecision(
        decision_id="d-1",
        application_id="app-1",
        outcome=DecisionOutcome.DECLINED,
        credit_score=Decimal("300"),
        approved_amount=None,
        approved_rate=None,
        decided_at=NOW,
        decided_by="system",
    )
    assert d.approved_amount is None
    assert d.approved_rate is None


def test_arrear_stage_enum_values() -> None:
    assert ArrearStage.CURRENT.value == "CURRENT"
    assert ArrearStage.DAYS_1_30.value == "DAYS_1_30"
    assert ArrearStage.DEFAULT_90_PLUS.value == "DEFAULT_90_PLUS"


def test_ifrs_stage_enum_values() -> None:
    assert IFRSStage.STAGE_1.value == "STAGE_1"
    assert IFRSStage.STAGE_2.value == "STAGE_2"
    assert IFRSStage.STAGE_3.value == "STAGE_3"


# ── InMemoryLoanProductStore ───────────────────────────────────────────────


def test_product_store_seeded_products() -> None:
    store = InMemoryLoanProductStore()
    products = store.list_products()
    assert len(products) == 3


def test_product_store_get_product_001() -> None:
    store = InMemoryLoanProductStore()
    p = store.get("product-001")
    assert p is not None
    assert p.max_amount == Decimal("2000")
    assert p.product_type == LoanProductType.MICRO_LOAN


def test_product_store_get_product_002() -> None:
    store = InMemoryLoanProductStore()
    p = store.get("product-002")
    assert p is not None
    assert p.max_amount == Decimal("15000")
    assert p.min_credit_score == Decimal("600")


def test_product_store_get_product_003() -> None:
    store = InMemoryLoanProductStore()
    p = store.get("product-003")
    assert p is not None
    assert p.product_type == LoanProductType.CREDIT_LINE
    assert p.max_term_months == 24


def test_product_store_get_nonexistent_returns_none() -> None:
    store = InMemoryLoanProductStore()
    assert store.get("does-not-exist") is None


# ── InMemoryLoanApplicationStore ──────────────────────────────────────────


def test_application_store_save_and_get() -> None:
    store = InMemoryLoanApplicationStore()
    app = LoanApplication(
        application_id="app-99",
        customer_id="cust-1",
        product_id="p-1",
        requested_amount=Decimal("500"),
        requested_term_months=6,
        status=LoanStatus.PENDING,
        applied_at=NOW,
    )
    store.save(app)
    assert store.get("app-99") is app


def test_application_store_list_by_customer() -> None:
    store = InMemoryLoanApplicationStore()
    for i in range(3):
        app = LoanApplication(
            application_id=f"app-{i}",
            customer_id="cust-X",
            product_id="p-1",
            requested_amount=Decimal("500"),
            requested_term_months=6,
            status=LoanStatus.PENDING,
            applied_at=NOW,
        )
        store.save(app)
    results = store.list_by_customer("cust-X")
    assert len(results) == 3


def test_provision_record_creation() -> None:
    r = ProvisionRecord(
        record_id="pr-1",
        application_id="app-1",
        ifrs_stage=IFRSStage.STAGE_1,
        ecl_amount=Decimal("45"),
        probability_of_default=Decimal("0.01"),
        exposure_at_default=Decimal("5000"),
        computed_at=NOW,
    )
    assert r.ecl_amount == Decimal("45")
    assert isinstance(r.ecl_amount, Decimal)


def test_repayment_type_enum_values() -> None:
    assert RepaymentType.ANNUITY.value == "ANNUITY"
    assert RepaymentType.LINEAR.value == "LINEAR"
