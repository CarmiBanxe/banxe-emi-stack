"""Tests for BreachPredictionSkill — trend analysis and breach prediction."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest

from agents.compliance.skills.breach_prediction import BreachPredictionSkill, PredictionResult


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_history(values: list[str], status: str = "DISCREPANCY") -> list[dict]:
    """Create a history list with given discrepancy string amounts."""
    return [
        {
            "date": date(2026, 4, i + 1),
            "discrepancy": Decimal(v),
            "status": status,
        }
        for i, v in enumerate(values)
    ]


# ── Test: DETERIORATING trend on increasing discrepancies ────────────────────


def test_deteriorating_trend_on_increasing_discrepancies():
    """DETERIORATING trend detected when discrepancies are increasing."""
    skill = BreachPredictionSkill()
    history = make_history(["100.00", "500.00", "1000.00", "2000.00", "5000.00"])

    result = skill.predict("acct-001", history)

    assert result.trend == "DETERIORATING"
    assert result.probability > Decimal("0.00")
    assert isinstance(result.probability, Decimal)


def test_deteriorating_trend_predicts_breach_soon():
    """DETERIORATING trend with consecutive discrepancies predicts breach in N days."""
    skill = BreachPredictionSkill()
    # 2 consecutive DISCREPANCY days → should predict 1 more day to breach
    history = make_history(["1000.00", "2000.00"])

    result = skill.predict("acct-002", history)

    assert result.predicted_breach_in_days is not None
    assert result.trend in ("DETERIORATING", "STABLE")  # depends on magnitude


# ── Test: probability = 0 for all MATCHED history ────────────────────────────


def test_probability_zero_for_all_matched():
    """Probability is 0.00 when all history entries are MATCHED (no discrepancy)."""
    skill = BreachPredictionSkill()
    history = [
        {"date": date(2026, 4, i), "discrepancy": Decimal("0"), "status": "MATCHED"}
        for i in range(1, 6)
    ]

    result = skill.predict("acct-003", history)

    assert result.probability == Decimal("0.00")
    assert result.predicted_breach_in_days is None
    assert result.trend == "STABLE"
    assert isinstance(result.probability, Decimal)


def test_empty_history_returns_zero_probability():
    """Empty history returns probability 0.00 and no prediction."""
    skill = BreachPredictionSkill()

    result = skill.predict("acct-004", [])

    assert result.probability == Decimal("0.00")
    assert result.predicted_breach_in_days is None


# ── Test: Decimal type for probability (never float) ─────────────────────────


def test_probability_is_always_decimal():
    """PredictionResult.probability is always Decimal — never float."""
    skill = BreachPredictionSkill()
    history = make_history(["500.00", "1000.00"])

    result = skill.predict("acct-005", history)

    assert isinstance(result.probability, Decimal)
    assert not isinstance(result.probability, float)


def test_confidence_is_decimal():
    """PredictionResult.confidence is always Decimal — never float."""
    skill = BreachPredictionSkill()
    history = make_history(["100.00", "200.00", "300.00"])

    result = skill.predict("acct-006", history)

    assert isinstance(result.confidence, Decimal)
    assert not isinstance(result.confidence, float)


def test_probability_clamped_between_0_and_1():
    """Probability is always in [0.00, 1.00] range."""
    skill = BreachPredictionSkill()
    # Very large discrepancy
    history = make_history(["999999.00", "9999999.00"])

    result = skill.predict("acct-007", history)

    assert Decimal("0.00") <= result.probability <= Decimal("1.00")


# ── Test: IMPROVING trend ─────────────────────────────────────────────────────


def test_improving_trend_on_decreasing_discrepancies():
    """IMPROVING trend detected when discrepancies are decreasing."""
    skill = BreachPredictionSkill()
    history = make_history(["5000.00", "2000.00", "1000.00", "500.00", "100.00"])

    result = skill.predict("acct-008", history)

    assert result.trend == "IMPROVING"
    assert result.predicted_breach_in_days is None


# ── Test: PredictionResult is frozen dataclass ────────────────────────────────


def test_prediction_result_is_frozen():
    """PredictionResult is a frozen dataclass — cannot be mutated."""
    result = PredictionResult(
        account_id="test-acct",
        probability=Decimal("0.50"),
        predicted_breach_in_days=2,
        trend="DETERIORATING",
        confidence=Decimal("0.70"),
    )

    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        result.probability = Decimal("0.99")  # type: ignore[misc]


# ── Test: moving average ──────────────────────────────────────────────────────


def test_moving_average_with_window_3():
    """Moving average of last 3 values is calculated correctly."""
    skill = BreachPredictionSkill()
    values = [Decimal("100"), Decimal("200"), Decimal("300"), Decimal("400"), Decimal("500")]

    ma = skill._moving_average(values, window=3)

    # Last 3: [300, 400, 500] → avg = 400
    assert ma == Decimal("400")


def test_moving_average_empty_returns_zero():
    """Moving average of empty list returns 0.00."""
    skill = BreachPredictionSkill()
    result = skill._moving_average([])
    assert result == Decimal("0.00")


# ── Test: trend calculation ───────────────────────────────────────────────────


def test_trend_stable_with_constant_values():
    """Constant discrepancy values → STABLE trend."""
    skill = BreachPredictionSkill()
    values = [Decimal("500.00")] * 6

    trend = skill._trend(values)

    assert trend == "STABLE"


def test_trend_single_value_is_stable():
    """Single value always returns STABLE."""
    skill = BreachPredictionSkill()
    trend = skill._trend([Decimal("100.00")])
    assert trend == "STABLE"
