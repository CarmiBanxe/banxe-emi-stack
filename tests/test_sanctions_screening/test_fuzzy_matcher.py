"""Tests for FuzzyMatcher — Phase 46 (IL-SRS-01)."""

from __future__ import annotations

from decimal import Decimal

from services.sanctions_screening.fuzzy_matcher import (
    HIGH_THRESHOLD,
    LOW_THRESHOLD,
    MEDIUM_THRESHOLD,
    FuzzyMatcher,
)
from services.sanctions_screening.models import MatchConfidence


def make_matcher():
    return FuzzyMatcher()


# --- Thresholds are Decimal (I-01) ---


def test_low_threshold_is_decimal():
    assert isinstance(LOW_THRESHOLD, Decimal)


def test_medium_threshold_is_decimal():
    assert isinstance(MEDIUM_THRESHOLD, Decimal)


def test_high_threshold_is_decimal():
    assert isinstance(HIGH_THRESHOLD, Decimal)


# --- match_name ---


def test_match_name_exact_match():
    m = make_matcher()
    score = m.match_name("Ivan Petrov", "Ivan Petrov")
    assert score == Decimal("100.00")


def test_match_name_no_match():
    m = make_matcher()
    score = m.match_name("AAAA", "ZZZZ")
    assert score < Decimal("50")


def test_match_name_returns_decimal():
    m = make_matcher()
    score = m.match_name("Test", "Test")
    assert isinstance(score, Decimal)


def test_match_name_case_insensitive():
    m = make_matcher()
    score1 = m.match_name("ivan petrov", "IVAN PETROV")
    score2 = m.match_name("Ivan Petrov", "Ivan Petrov")
    assert score1 == score2


def test_match_name_partial():
    m = make_matcher()
    score = m.match_name("Ivan Petrov", "Ivan")
    assert Decimal("0") < score < Decimal("100")


# --- match_dob ---


def test_match_dob_exact():
    m = make_matcher()
    assert m.match_dob("1990-01-01", "1990-01-01") is True


def test_match_dob_different():
    m = make_matcher()
    assert m.match_dob("1990-01-01", "1991-01-01") is False


def test_match_dob_with_spaces():
    m = make_matcher()
    assert m.match_dob("1990-01-01 ", " 1990-01-01") is True


# --- match_nationality ---


def test_match_nationality_exact():
    m = make_matcher()
    assert m.match_nationality("GB", "GB") is True


def test_match_nationality_case():
    m = make_matcher()
    assert m.match_nationality("gb", "GB") is True


def test_match_nationality_different():
    m = make_matcher()
    assert m.match_nationality("GB", "US") is False


# --- calculate_composite_score ---


def test_composite_score_all_match():
    m = make_matcher()
    score = m.calculate_composite_score(Decimal("100"), True, True)
    assert score == Decimal("100.00")


def test_composite_score_name_only():
    m = make_matcher()
    score = m.calculate_composite_score(Decimal("100"), False, False)
    assert score == Decimal("60.00")  # 100 * 0.6


def test_composite_score_is_decimal():
    m = make_matcher()
    score = m.calculate_composite_score(Decimal("80"), True, False)
    assert isinstance(score, Decimal)


def test_composite_score_dob_weight():
    m = make_matcher()
    score = m.calculate_composite_score(Decimal("0"), True, False)
    assert score == Decimal("30.00")  # 100 * 0.3


# --- configure_thresholds ---


def test_configure_thresholds():
    m = make_matcher()
    m.configure_thresholds(Decimal("30"), Decimal("60"), Decimal("80"))
    assert m._low == Decimal("30")
    assert m._medium == Decimal("60")
    assert m._high == Decimal("80")


# --- classify_confidence ---


def test_classify_confidence_low():
    m = make_matcher()
    assert m.classify_confidence(Decimal("30")) == MatchConfidence.LOW
    assert m.classify_confidence(Decimal("64.99")) == MatchConfidence.LOW


def test_classify_confidence_medium():
    m = make_matcher()
    assert m.classify_confidence(Decimal("65")) == MatchConfidence.MEDIUM
    assert m.classify_confidence(Decimal("84.99")) == MatchConfidence.MEDIUM


def test_classify_confidence_high():
    m = make_matcher()
    assert m.classify_confidence(Decimal("85")) == MatchConfidence.HIGH
    assert m.classify_confidence(Decimal("100")) == MatchConfidence.HIGH
