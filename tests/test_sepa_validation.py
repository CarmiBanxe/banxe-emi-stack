"""Unit tests for services.payment.sepa_validation (ADR-102 single source of truth).

Pure validators — no network. Covers IBAN mod-97, BIC SWIFT format, SCT Instant €100k cap.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.payment.sepa_validation import (
    SCT_INSTANT_MAX_EUR,
    exceeds_sct_instant_cap,
    validate_bic,
    validate_iban,
)


@pytest.mark.parametrize(
    "iban",
    [
        "DE89370400440532013000",  # valid DE
        "GB29NWBK60161331926819",  # valid GB
        "FR1420041010050500013M02606",  # valid FR (alpha in BBAN)
        "de89 3704 0044 0532 0130 00",  # lowercase + spaces tolerated
    ],
)
def test_validate_iban_accepts_valid(iban):
    assert validate_iban(iban) is True


@pytest.mark.parametrize(
    "iban",
    [
        "DE89370400440532013001",  # wrong check digits
        "XX00",  # too short / bad format
        "GB29NWBK6016133192681",  # one digit short
        "",  # empty
        "1234567890",  # no country code
    ],
)
def test_validate_iban_rejects_invalid(iban):
    assert validate_iban(iban) is False


@pytest.mark.parametrize("bic", ["NWBKGB2L", "NWBKGB2LXXX", "deutdeff", "DEUTDEFF500"])
def test_validate_bic_accepts_valid(bic):
    assert validate_bic(bic) is True


@pytest.mark.parametrize("bic", ["NWBK", "NWBKGB2", "NWBKGB2LXX", "12BKGB2L", ""])
def test_validate_bic_rejects_invalid(bic):
    assert validate_bic(bic) is False


def test_sct_instant_cap_value():
    assert Decimal("100000.00") == SCT_INSTANT_MAX_EUR


@pytest.mark.parametrize(
    ("amount", "is_instant", "expected"),
    [
        (Decimal("100000.00"), True, False),  # exactly at cap → allowed
        (Decimal("100000.01"), True, True),  # over cap → exceeds
        (Decimal("250000.00"), True, True),  # well over → exceeds
        (Decimal("250000.00"), False, False),  # SCT (non-instant) → cap does not apply
        (Decimal("0.01"), True, False),  # tiny instant → fine
    ],
)
def test_exceeds_sct_instant_cap(amount, is_instant, expected):
    assert exceeds_sct_instant_cap(amount, is_instant=is_instant) is expected
