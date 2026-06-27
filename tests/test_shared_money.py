"""Unit tests for services.shared.money.to_minor_units (ADR-102 de-dup canonical impl).

Covers: Decimal-only guard (I-01), all configured currencies + unlisted default (2dp),
and ROUND_HALF_UP behaviour. No pragmas, no network.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.shared.money import to_minor_units


@pytest.mark.parametrize(
    ("amount", "currency", "expected"),
    [
        (Decimal("10.00"), "GBP", 1000),
        (Decimal("10.00"), "EUR", 1000),
        (Decimal("10.00"), "USD", 1000),
        (Decimal("10.00"), "CHF", 1000),
        (Decimal("0"), "GBP", 0),
        (Decimal("1.005"), "GBP", 101),  # ROUND_HALF_UP at 2dp
        (Decimal("1.004"), "GBP", 100),
        (Decimal("99.99"), "eur", 9999),  # case-insensitive currency
        (Decimal("5.50"), "JPY", 550),  # unlisted → default 2dp
    ],
)
def test_to_minor_units_values(amount, currency, expected):
    assert to_minor_units(amount, currency) == expected


def test_to_minor_units_rejects_non_decimal():
    """I-01: amount must be Decimal — float/int/str raise TypeError (never float money)."""
    for bad in (10.0, 10, "10.00"):
        with pytest.raises(TypeError):
            to_minor_units(bad, "GBP")  # type: ignore[arg-type]


def test_returns_int():
    assert isinstance(to_minor_units(Decimal("1.23"), "USD"), int)
