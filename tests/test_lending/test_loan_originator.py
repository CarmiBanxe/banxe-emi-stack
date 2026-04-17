"""
tests/test_lending/test_loan_originator.py — Unit tests for LoanOriginator
IL-LCE-01 | Phase 25

20 tests covering apply, decide, disburse, and HITL requirement.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.lending.credit_scorer import CreditScorer
from services.lending.loan_originator import LoanOriginator
from services.lending.models import (
    DecisionOutcome,
    LoanStatus,
)


def _make_originator() -> LoanOriginator:
    return LoanOriginator()


def _score(
    income: Decimal = Decimal("35000"), age: int = 24, aml: Decimal = Decimal("10")
) -> object:
    scorer = CreditScorer()
    return scorer.score_customer("cust-1", income, age, aml)


# ── apply ──────────────────────────────────────────────────────────────────


def test_apply_creates_pending_application() -> None:
    orig = _make_originator()
    app = orig.apply("cust-1", "product-001", Decimal("1000"), 6)
    assert app.status == LoanStatus.PENDING


def test_apply_stores_correct_fields() -> None:
    orig = _make_originator()
    app = orig.apply("cust-1", "product-001", Decimal("500"), 6)
    assert app.customer_id == "cust-1"
    assert app.product_id == "product-001"
    assert app.requested_amount == Decimal("500")
    assert app.requested_term_months == 6


def test_apply_generates_unique_ids() -> None:
    orig = _make_originator()
    app1 = orig.apply("cust-1", "product-001", Decimal("500"), 6)
    app2 = orig.apply("cust-2", "product-001", Decimal("500"), 6)
    assert app1.application_id != app2.application_id


def test_apply_amount_at_max_is_valid() -> None:
    orig = _make_originator()
    app = orig.apply("cust-1", "product-001", Decimal("2000"), 12)
    assert app.status == LoanStatus.PENDING


def test_apply_amount_exceeds_max_raises() -> None:
    orig = _make_originator()
    with pytest.raises(ValueError, match="exceeds product max"):
        orig.apply("cust-1", "product-001", Decimal("2001"), 12)


def test_apply_term_exceeds_max_raises() -> None:
    orig = _make_originator()
    with pytest.raises(ValueError, match="exceeds product max"):
        orig.apply("cust-1", "product-001", Decimal("1000"), 13)


def test_apply_unknown_product_raises() -> None:
    orig = _make_originator()
    with pytest.raises(ValueError, match="Product not found"):
        orig.apply("cust-1", "product-999", Decimal("1000"), 6)


def test_apply_requested_amount_is_decimal() -> None:
    orig = _make_originator()
    app = orig.apply("cust-1", "product-001", Decimal("750"), 6)
    assert isinstance(app.requested_amount, Decimal)


# ── decide ─────────────────────────────────────────────────────────────────


def test_decide_always_returns_hitl_required() -> None:
    orig = _make_originator()
    app = orig.apply("cust-1", "product-001", Decimal("1000"), 6)
    score = _score()
    result = orig.decide(app.application_id, score)
    assert result["status"] == "HITL_REQUIRED"


def test_decide_above_min_score_approves() -> None:
    orig = _make_originator()
    app = orig.apply("cust-1", "product-001", Decimal("1000"), 6)
    # product-001 min_credit_score=500; score with good income will be ~770+
    score = _score(income=Decimal("35000"), age=24, aml=Decimal("10"))
    result = orig.decide(app.application_id, score)
    assert result["decision"].outcome == DecisionOutcome.APPROVED


def test_decide_below_min_score_declines() -> None:
    orig = _make_originator()
    app = orig.apply("cust-1", "product-001", Decimal("1000"), 6)
    # Score with zero income, zero history, max AML risk = 0
    score = _score(income=Decimal("0"), age=0, aml=Decimal("100"))
    result = orig.decide(app.application_id, score)
    assert result["decision"].outcome == DecisionOutcome.DECLINED


def test_decide_updates_application_status_on_approve() -> None:
    orig = _make_originator()
    app = orig.apply("cust-1", "product-001", Decimal("1000"), 6)
    score = _score()
    result = orig.decide(app.application_id, score)
    assert result["application"].status == LoanStatus.APPROVED


def test_decide_updates_application_status_on_decline() -> None:
    orig = _make_originator()
    app = orig.apply("cust-1", "product-001", Decimal("1000"), 6)
    score = _score(income=Decimal("0"), age=0, aml=Decimal("100"))
    result = orig.decide(app.application_id, score)
    assert result["application"].status == LoanStatus.DECLINED


def test_decide_nonexistent_application_raises() -> None:
    orig = _make_originator()
    score = _score()
    with pytest.raises(ValueError, match="Application not found"):
        orig.decide("app-does-not-exist", score)


def test_decide_non_pending_application_raises() -> None:
    orig = _make_originator()
    app = orig.apply("cust-1", "product-001", Decimal("1000"), 6)
    score = _score()
    orig.decide(app.application_id, score)
    # Second decide on same application (now APPROVED/DECLINED) should fail
    with pytest.raises(ValueError, match="not in PENDING status"):
        orig.decide(app.application_id, score)


def test_decide_approved_amount_is_decimal() -> None:
    orig = _make_originator()
    app = orig.apply("cust-1", "product-001", Decimal("1000"), 6)
    score = _score()
    result = orig.decide(app.application_id, score)
    if result["decision"].approved_amount is not None:
        assert isinstance(result["decision"].approved_amount, Decimal)


# ── disburse ───────────────────────────────────────────────────────────────


def test_disburse_approved_application_succeeds() -> None:
    orig = _make_originator()
    app = orig.apply("cust-1", "product-001", Decimal("1000"), 6)
    score = _score()
    result = orig.decide(app.application_id, score)
    assert result["application"].status == LoanStatus.APPROVED
    disbursed = orig.disburse(result["application"].application_id, actor="officer")
    assert disbursed.status == LoanStatus.DISBURSED


def test_disburse_non_approved_raises() -> None:
    orig = _make_originator()
    app = orig.apply("cust-1", "product-001", Decimal("1000"), 6)
    # PENDING → cannot disburse
    with pytest.raises(ValueError, match="Cannot disburse"):
        orig.disburse(app.application_id, actor="officer")


def test_disburse_nonexistent_application_raises() -> None:
    orig = _make_originator()
    with pytest.raises(ValueError, match="Application not found"):
        orig.disburse("app-ghost", actor="officer")


def test_get_application_returns_none_for_unknown() -> None:
    orig = _make_originator()
    assert orig.get_application("not-there") is None
