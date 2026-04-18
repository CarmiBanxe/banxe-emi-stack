"""
tests/test_batch_payments/test_limit_checker.py — Tests for LimitChecker
IL-BPP-01 | Phase 36 | 16 tests
I-04: AML threshold £10k. I-01: Decimal amounts.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from services.batch_payments.limit_checker import (
    AML_THRESHOLD_GBP,
    BATCH_LIMIT_GBP,
    DAILY_AGGREGATE_LIMIT_GBP,
    LimitChecker,
)


@pytest.fixture()
def checker():
    return LimitChecker()


def test_batch_limit_value():
    assert Decimal("500000") == BATCH_LIMIT_GBP


def test_daily_limit_value():
    assert Decimal("2000000") == DAILY_AGGREGATE_LIMIT_GBP


def test_aml_threshold_value():
    assert Decimal("10000") == AML_THRESHOLD_GBP


def test_check_batch_limit_pass(checker):
    assert checker.check_batch_limit(Decimal("499999")) is True


def test_check_batch_limit_at_boundary(checker):
    assert checker.check_batch_limit(Decimal("500000")) is True


def test_check_batch_limit_exceeds(checker):
    assert checker.check_batch_limit(Decimal("500001")) is False


def test_check_daily_limit_first_batch_passes(checker):
    today = date(2026, 4, 17)
    assert checker.check_daily_limit("user-1", today, Decimal("1000000")) is True


def test_check_daily_limit_two_batches_within(checker):
    today = date(2026, 4, 17)
    checker.check_daily_limit("user-2", today, Decimal("1000000"))
    assert checker.check_daily_limit("user-2", today, Decimal("999999")) is True


def test_check_daily_limit_exceeds(checker):
    today = date(2026, 4, 17)
    checker.check_daily_limit("user-3", today, Decimal("1500000"))
    assert checker.check_daily_limit("user-3", today, Decimal("600000")) is False


def test_check_aml_threshold_at_10k(checker):
    assert checker.check_aml_threshold(Decimal("10000")) is True


def test_check_aml_threshold_above_10k(checker):
    assert checker.check_aml_threshold(Decimal("10001")) is True


def test_check_aml_threshold_below_10k(checker):
    assert checker.check_aml_threshold(Decimal("9999.99")) is False


def test_check_velocity_first_batch_passes(checker):
    assert checker.check_velocity("user-v1") is True


def test_check_velocity_ten_batches_allowed(checker):
    for _ in range(9):
        checker.check_velocity("user-v2")
    assert checker.check_velocity("user-v2") is True


def test_check_velocity_eleventh_batch_rejected(checker):
    for _ in range(10):
        checker.check_velocity("user-v3")
    assert checker.check_velocity("user-v3") is False


def test_get_limit_summary_has_all_keys(checker):
    summary = checker.get_limit_summary()
    assert "batch_limit_gbp" in summary
    assert "daily_aggregate_limit_gbp" in summary
    assert "aml_threshold_gbp" in summary
    assert "max_batches_per_24h" in summary


def test_check_daily_limit_amounts_are_decimal(checker):
    today = date(2026, 4, 17)
    result = checker.check_daily_limit("user-dec", today, Decimal("100"))
    assert isinstance(result, bool)
