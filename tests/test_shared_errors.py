"""
tests/test_shared_errors.py — BanxeLegacyAdapterError hierarchy tests (F-03).

Verifies:
  1. BanxeLegacyAdapterError itself imports and raises correctly.
  2. All 5 unified adapter error classes are isinstance-compatible.
  3. Existing catch patterns (by specific type, by Exception) still work — backward compat.
  4. .code attribute preserved on all classes.
  5. str(exc) returns the original message (no double-wrapping).
"""

from __future__ import annotations

import pytest

from services.shared.errors import BanxeLegacyAdapterError

# ── 1. Base class ─────────────────────────────────────────────────────────────


def test_base_error_instantiates() -> None:
    err = BanxeLegacyAdapterError("base failure", code="base_err")
    assert str(err) == "base failure"
    assert err.code == "base_err"


def test_base_error_is_exception() -> None:
    err = BanxeLegacyAdapterError("x", code="y")
    assert isinstance(err, Exception)


def test_base_error_raises_and_catches() -> None:
    with pytest.raises(BanxeLegacyAdapterError) as exc_info:
        raise BanxeLegacyAdapterError("boom", code="test_code")
    assert exc_info.value.code == "test_code"


# ── 2. Wave C — TransactionApplicationError ───────────────────────────────────


def test_transaction_error_is_banxe_base() -> None:
    from services.payment.legacy.legacy_transactions_adapter import TransactionApplicationError

    err = TransactionApplicationError("tx failed", code="transaction_not_found")
    assert isinstance(err, BanxeLegacyAdapterError)


def test_transaction_error_code_preserved() -> None:
    from services.payment.legacy.legacy_transactions_adapter import TransactionApplicationError

    err = TransactionApplicationError("not found", code="transaction_not_found")
    assert err.code == "transaction_not_found"
    assert str(err) == "not found"


def test_transaction_error_catchable_as_specific() -> None:
    from services.payment.legacy.legacy_transactions_adapter import TransactionApplicationError

    with pytest.raises(TransactionApplicationError):
        raise TransactionApplicationError("fail", code="x")


# ── 3. Wave C — AbsApplicationError ──────────────────────────────────────────


def test_abs_error_is_banxe_base() -> None:
    from services.payment.legacy.legacy_abs_payment_adapter import AbsApplicationError

    err = AbsApplicationError("abs fail", code="unsupported_rail")
    assert isinstance(err, BanxeLegacyAdapterError)


def test_abs_error_code_preserved() -> None:
    from services.payment.legacy.legacy_abs_payment_adapter import AbsApplicationError

    err = AbsApplicationError("bad rail", code="unsupported_rail")
    assert err.code == "unsupported_rail"
    assert str(err) == "bad rail"


# ── 4. Wave C — SepaApplicationError ─────────────────────────────────────────


def test_sepa_error_is_banxe_base() -> None:
    from services.payment.legacy.legacy_sepa_adapter import SepaApplicationError

    err = SepaApplicationError("sepa fail", code="invalid_iban")
    assert isinstance(err, BanxeLegacyAdapterError)


def test_sepa_error_code_preserved() -> None:
    from services.payment.legacy.legacy_sepa_adapter import SepaApplicationError

    err = SepaApplicationError("bad IBAN", code="invalid_iban")
    assert err.code == "invalid_iban"
    assert str(err) == "bad IBAN"


def test_sepa_error_catchable_as_specific() -> None:
    from services.payment.legacy.legacy_sepa_adapter import SepaApplicationError

    with pytest.raises(SepaApplicationError):
        raise SepaApplicationError("fail", code="x")


# ── 5. Wave D — SumSubApplicationError ───────────────────────────────────────


def test_sumsub_error_is_banxe_base() -> None:
    from services.compliance.legacy.legacy_sumsub_adapter import SumSubApplicationError

    err = SumSubApplicationError("kyc fail", code="blocked_country")
    assert isinstance(err, BanxeLegacyAdapterError)


def test_sumsub_error_code_preserved() -> None:
    from services.compliance.legacy.legacy_sumsub_adapter import SumSubApplicationError

    err = SumSubApplicationError("blocked", code="blocked_country")
    assert err.code == "blocked_country"
    assert str(err) == "blocked"


# ── 6. Wave D — BinanceKYCError ──────────────────────────────────────────────


def test_binance_error_is_banxe_base() -> None:
    from services.compliance.legacy.legacy_binancekyc_adapter import BinanceKYCError

    err = BinanceKYCError("kyc error", code="blocked_country")
    assert isinstance(err, BanxeLegacyAdapterError)


def test_binance_error_code_preserved() -> None:
    from services.compliance.legacy.legacy_binancekyc_adapter import BinanceKYCError

    err = BinanceKYCError("blocked", code="blocked_country")
    assert err.code == "blocked_country"
    assert str(err) == "blocked"


def test_binance_error_catchable_as_specific() -> None:
    from services.compliance.legacy.legacy_binancekyc_adapter import BinanceKYCError

    with pytest.raises(BinanceKYCError):
        raise BinanceKYCError("fail", code="x")


# ── 7. Cross-wave catch by base ───────────────────────────────────────────────


def test_all_five_catchable_as_banxe_base() -> None:
    from services.compliance.legacy.legacy_binancekyc_adapter import BinanceKYCError
    from services.compliance.legacy.legacy_sumsub_adapter import SumSubApplicationError
    from services.payment.legacy.legacy_abs_payment_adapter import AbsApplicationError
    from services.payment.legacy.legacy_sepa_adapter import SepaApplicationError
    from services.payment.legacy.legacy_transactions_adapter import TransactionApplicationError

    errors = [
        TransactionApplicationError("tx", code="c"),
        AbsApplicationError("abs", code="c"),
        SepaApplicationError("sepa", code="c"),
        SumSubApplicationError("sumsub", code="c"),
        BinanceKYCError("binance", code="c"),
    ]
    for err in errors:
        assert isinstance(err, BanxeLegacyAdapterError), (
            f"{type(err)} not a BanxeLegacyAdapterError"
        )
        assert isinstance(err, Exception)


def test_cross_wave_catch_pattern() -> None:
    """Single except BanxeLegacyAdapterError catches any Wave-C/D adapter error."""
    from services.payment.legacy.legacy_sepa_adapter import SepaApplicationError

    caught: list[BanxeLegacyAdapterError] = []
    try:
        raise SepaApplicationError("bad IBAN", code="invalid_iban")
    except BanxeLegacyAdapterError as exc:
        caught.append(exc)

    assert len(caught) == 1
    assert caught[0].code == "invalid_iban"
