"""Shared money utilities — single canonical minor-unit conversion (ADR-102 de-dup).

Canonical home for `to_minor_units`, previously duplicated in
`services/payment/legacy/bifrost_adapter.py` and `services/open_banking/m24_int_bridge.py`
(identical logic; differing only in `_MINOR_UNITS` coverage — consolidated to the superset here).

Money invariants:
  - I-01: amounts are `Decimal` upstream — never `float`.
  - I-05: minor units are `int` (the smallest currency unit), derived deterministically.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

# ISO 4217 minor-unit exponents (config-as-data; default 2dp for unlisted currencies).
_MINOR_UNITS: dict[str, int] = {"EUR": 2, "GBP": 2, "USD": 2, "CHF": 2}


def to_minor_units(amount: Decimal, currency: str) -> int:
    """Convert a Decimal major-unit amount to integer minor units (I-01 in, I-05 out; never float).

    Half-up rounding at the currency's minor-unit precision (default 2dp). Raises `TypeError`
    if `amount` is not a `Decimal` (Decimal-only upstream, I-01).
    """
    if not isinstance(amount, Decimal):  # I-01: Decimal only
        raise TypeError("amount must be Decimal")
    dp = _MINOR_UNITS.get(currency.upper(), 2)
    return int((amount * (Decimal(10) ** dp)).to_integral_value(rounding=ROUND_HALF_UP))
