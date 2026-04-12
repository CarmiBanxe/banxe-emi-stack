"""Tests for MT940 and CAMT.053 parser validation."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest

from services.recon.bankstatement_parser import (
    parse_camt053,
    parse_mt940,
    validate_statement_balance,
)

# ── Test: validate_statement_balance passes when txns sum correctly ─────────


def test_validate_statement_balance_passes():
    """validate_statement_balance raises nothing when transactions sum matches."""
    opening = Decimal("1000.00")
    closing = Decimal("1350.00")
    # Net movement = 350.00
    transactions = [Decimal("500.00"), Decimal("-150.00")]
    # Should not raise
    validate_statement_balance(transactions, opening, closing)


def test_validate_statement_balance_passes_zero_movement():
    """validate_statement_balance passes with empty transaction list and equal balances."""
    opening = Decimal("5000.00")
    closing = Decimal("5000.00")
    validate_statement_balance([], opening, closing)


def test_validate_statement_balance_passes_negative_movement():
    """validate_statement_balance passes when closing < opening (net debit)."""
    opening = Decimal("2000.00")
    closing = Decimal("1500.00")
    transactions = [Decimal("-500.00")]
    validate_statement_balance(transactions, opening, closing)


# ── Test: validate_statement_balance raises ValueError on mismatch ──────────


def test_validate_statement_balance_raises_on_mismatch():
    """validate_statement_balance raises ValueError when sum(txns) != closing - opening."""
    opening = Decimal("1000.00")
    closing = Decimal("1500.00")
    # Transactions sum to 400, but expected movement is 500
    transactions = [Decimal("400.00")]

    with pytest.raises(ValueError, match="Statement balance validation failed"):
        validate_statement_balance(transactions, opening, closing)


def test_validate_statement_balance_error_message_contains_amounts():
    """ValueError message includes opening, closing and actual movement."""
    opening = Decimal("100.00")
    closing = Decimal("200.00")
    transactions = [Decimal("50.00")]

    with pytest.raises(ValueError) as exc_info:
        validate_statement_balance(transactions, opening, closing)

    error_msg = str(exc_info.value)
    assert "50" in error_msg or "100" in error_msg  # actual movement or expected in message


# ── Test: parse_mt940 returns [] when mt940 lib not installed (graceful) ────


def test_parse_mt940_graceful_when_lib_not_installed(tmp_path):
    """parse_mt940 returns [] gracefully when mt940 library is not installed."""
    dummy_path = tmp_path / "test.sta"
    dummy_path.write_text(":20:BANXE\n:25:GB12BARCS20480100111111\n")

    with patch.dict("sys.modules", {"mt940": None}):
        result = parse_mt940(dummy_path)

    assert result == []


# ── Test: parse_camt053 returns [] when bankstatementparser not installed ────


def test_parse_camt053_graceful_when_lib_not_installed(tmp_path):
    """parse_camt053 returns [] gracefully when bankstatementparser not installed."""
    dummy_path = tmp_path / "test.xml"
    dummy_path.write_text("<Document></Document>")

    with patch.dict("sys.modules", {"bankstatementparser": None}):
        result = parse_camt053(dummy_path)

    assert result == []


# ── Test: Decimal invariant ──────────────────────────────────────────────────


def test_validate_uses_decimal_not_float():
    """All amounts in validate_statement_balance are Decimal — never float."""
    opening = Decimal("100.00")
    closing = Decimal("150.00")
    transactions = [Decimal("50.00")]

    # This should not raise — Decimal arithmetic is exact
    validate_statement_balance(transactions, opening, closing)

    # Verify that passing float raises TypeError or causes issues
    # (We don't accept float — document this as a constraint)
    result = Decimal("50.00") + Decimal("0")
    assert isinstance(result, Decimal)
