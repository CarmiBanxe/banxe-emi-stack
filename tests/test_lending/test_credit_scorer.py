"""
tests/test_lending/test_credit_scorer.py — Unit tests for CreditScorer
IL-LCE-01 | Phase 25

18 tests covering scoring ranges, boundary conditions, edge cases,
and Decimal-only invariant.
"""

from __future__ import annotations

from decimal import Decimal

from services.lending.credit_scorer import CreditScorer
from services.lending.models import CreditScore


def test_score_customer_returns_credit_score() -> None:
    scorer = CreditScorer()
    score = scorer.score_customer("cust-1", Decimal("35000"), 24, Decimal("10"))
    assert isinstance(score, CreditScore)


def test_score_customer_total_is_decimal() -> None:
    scorer = CreditScorer()
    score = scorer.score_customer("cust-1", Decimal("35000"), 24, Decimal("10"))
    assert isinstance(score.score, Decimal)
    assert isinstance(score.income_factor, Decimal)
    assert isinstance(score.history_factor, Decimal)
    assert isinstance(score.aml_risk_factor, Decimal)


def test_score_customer_max_income_full_income_factor() -> None:
    scorer = CreditScorer()
    # income >= 50000 → income_factor = 400
    score = scorer.score_customer("cust-1", Decimal("50000"), 0, Decimal("100"))
    assert score.income_factor == Decimal("400")


def test_score_customer_zero_income_zero_income_factor() -> None:
    scorer = CreditScorer()
    score = scorer.score_customer("cust-1", Decimal("0"), 24, Decimal("0"))
    assert score.income_factor == Decimal("0")


def test_score_customer_max_account_age_full_history_factor() -> None:
    scorer = CreditScorer()
    score = scorer.score_customer("cust-1", Decimal("0"), 24, Decimal("100"))
    assert score.history_factor == Decimal("300")


def test_score_customer_zero_account_age_zero_history_factor() -> None:
    scorer = CreditScorer()
    score = scorer.score_customer("cust-1", Decimal("50000"), 0, Decimal("100"))
    assert score.history_factor == Decimal("0")


def test_score_customer_zero_aml_risk_full_aml_factor() -> None:
    scorer = CreditScorer()
    score = scorer.score_customer("cust-1", Decimal("0"), 0, Decimal("0"))
    assert score.aml_risk_factor == Decimal("300")


def test_score_customer_max_aml_risk_zero_aml_factor() -> None:
    scorer = CreditScorer()
    score = scorer.score_customer("cust-1", Decimal("0"), 0, Decimal("100"))
    assert score.aml_risk_factor == Decimal("0")


def test_score_customer_perfect_score_is_1000() -> None:
    scorer = CreditScorer()
    score = scorer.score_customer("cust-1", Decimal("50000"), 24, Decimal("0"))
    assert score.score == Decimal("1000")


def test_score_customer_zero_score_all_bad() -> None:
    scorer = CreditScorer()
    score = scorer.score_customer("cust-1", Decimal("0"), 0, Decimal("100"))
    assert score.score == Decimal("0")


def test_score_range_is_0_to_1000() -> None:
    scorer = CreditScorer()
    score = scorer.score_customer("cust-1", Decimal("25000"), 12, Decimal("50"))
    assert Decimal("0") <= score.score <= Decimal("1000")


def test_score_customer_high_aml_risk_lowers_score() -> None:
    scorer = CreditScorer()
    low_risk = scorer.score_customer("cust-A", Decimal("35000"), 24, Decimal("5"))
    high_risk = scorer.score_customer("cust-B", Decimal("35000"), 24, Decimal("95"))
    assert low_risk.score > high_risk.score


def test_score_customer_stores_result() -> None:
    scorer = CreditScorer()
    scorer.score_customer("cust-1", Decimal("35000"), 24, Decimal("10"))
    latest = scorer.get_latest_score("cust-1")
    assert latest is not None
    assert latest.customer_id == "cust-1"


def test_get_latest_score_returns_none_for_unscored() -> None:
    scorer = CreditScorer()
    assert scorer.get_latest_score("never-scored") is None


def test_score_customer_overwrites_previous_score() -> None:
    scorer = CreditScorer()
    scorer.score_customer("cust-1", Decimal("10000"), 6, Decimal("80"))
    scorer.score_customer("cust-1", Decimal("50000"), 24, Decimal("0"))
    latest = scorer.get_latest_score("cust-1")
    assert latest is not None
    assert latest.score == Decimal("1000")


def test_income_above_50k_caps_at_400() -> None:
    scorer = CreditScorer()
    score = scorer.score_customer("cust-1", Decimal("100000"), 0, Decimal("100"))
    assert score.income_factor == Decimal("400")


def test_account_age_above_24_caps_at_300() -> None:
    scorer = CreditScorer()
    score = scorer.score_customer("cust-1", Decimal("0"), 100, Decimal("100"))
    assert score.history_factor == Decimal("300")


def test_score_factors_sum_to_total() -> None:
    scorer = CreditScorer()
    score = scorer.score_customer("cust-1", Decimal("25000"), 12, Decimal("50"))
    expected = score.income_factor + score.history_factor + score.aml_risk_factor
    assert score.score == expected
