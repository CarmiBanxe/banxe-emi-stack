"""tests/test_fx_exchange/test_fx_compliance.py — FXCompliance tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.fx_exchange.fx_compliance import (
    _BLOCKED_CURRENCIES,
    _HITL_THRESHOLD,
    _LARGE_FX_THRESHOLD,
    FXCompliance,
)
from services.fx_exchange.models import ComplianceFlag, CurrencyPair


@pytest.fixture()
def compliance() -> FXCompliance:
    return FXCompliance()


# ── CLEAR threshold ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_order_below_threshold_is_clear(compliance):
    flag = await compliance.check_order("ent1", CurrencyPair("GBP", "EUR"), Decimal("9999"))
    assert flag == ComplianceFlag.CLEAR


@pytest.mark.asyncio
async def test_check_order_zero_amount_is_clear(compliance):
    flag = await compliance.check_order("ent1", CurrencyPair("GBP", "EUR"), Decimal("0"))
    assert flag == ComplianceFlag.CLEAR


@pytest.mark.asyncio
async def test_check_order_just_below_threshold_is_clear(compliance):
    flag = await compliance.check_order(
        "ent1", CurrencyPair("GBP", "EUR"), _LARGE_FX_THRESHOLD - Decimal("0.01")
    )
    assert flag == ComplianceFlag.CLEAR


# ── EDD_REQUIRED threshold (MLR 2017 §33) ─────────────────────────────────────


@pytest.mark.asyncio
async def test_check_order_at_large_threshold_edd(compliance):
    flag = await compliance.check_order("ent1", CurrencyPair("GBP", "EUR"), _LARGE_FX_THRESHOLD)
    assert flag == ComplianceFlag.EDD_REQUIRED


@pytest.mark.asyncio
async def test_check_order_above_large_threshold_edd(compliance):
    flag = await compliance.check_order("ent1", CurrencyPair("GBP", "EUR"), Decimal("25000"))
    assert flag == ComplianceFlag.EDD_REQUIRED


@pytest.mark.asyncio
async def test_check_order_at_hitl_threshold_edd(compliance):
    flag = await compliance.check_order("ent1", CurrencyPair("GBP", "EUR"), _HITL_THRESHOLD)
    assert flag == ComplianceFlag.EDD_REQUIRED


@pytest.mark.asyncio
async def test_check_order_above_hitl_threshold_edd(compliance):
    flag = await compliance.check_order("ent1", CurrencyPair("GBP", "EUR"), Decimal("100000"))
    assert flag == ComplianceFlag.EDD_REQUIRED


# ── BLOCKED sanctioned currencies ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_order_rub_in_base_blocked(compliance):
    flag = await compliance.check_order("ent1", CurrencyPair("RUB", "EUR"), Decimal("100"))
    assert flag == ComplianceFlag.BLOCKED


@pytest.mark.asyncio
async def test_check_order_rub_in_quote_blocked(compliance):
    flag = await compliance.check_order("ent1", CurrencyPair("GBP", "RUB"), Decimal("100"))
    assert flag == ComplianceFlag.BLOCKED


@pytest.mark.asyncio
async def test_check_order_irr_blocked(compliance):
    flag = await compliance.check_order("ent1", CurrencyPair("GBP", "IRR"), Decimal("1"))
    assert flag == ComplianceFlag.BLOCKED


@pytest.mark.asyncio
async def test_check_order_kpw_blocked(compliance):
    flag = await compliance.check_order("ent1", CurrencyPair("GBP", "KPW"), Decimal("1"))
    assert flag == ComplianceFlag.BLOCKED


@pytest.mark.asyncio
async def test_blocked_overrides_edd_threshold(compliance):
    # Even if amount is £0, blocked currency → BLOCKED (not CLEAR)
    flag = await compliance.check_order("ent1", CurrencyPair("GBP", "RUB"), Decimal("1"))
    assert flag == ComplianceFlag.BLOCKED


@pytest.mark.asyncio
async def test_blocked_currencies_set_contains_expected(compliance):
    assert "RUB" in _BLOCKED_CURRENCIES
    assert "IRR" in _BLOCKED_CURRENCIES
    assert "KPW" in _BLOCKED_CURRENCIES
    assert "SYP" in _BLOCKED_CURRENCIES
    assert "CUC" in _BLOCKED_CURRENCIES
    assert "BYR" in _BLOCKED_CURRENCIES


# ── Structuring detection ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detect_structuring_no_structuring_single_large(compliance):
    # One large amount ≥ threshold → NOT structuring (single transaction)
    result = await compliance.detect_structuring("ent1", [Decimal("15000")])
    assert result is False


@pytest.mark.asyncio
async def test_detect_structuring_detected(compliance):
    # Multiple amounts summing > threshold but each below → structuring
    amounts = [Decimal("3500"), Decimal("3500"), Decimal("3500")]
    result = await compliance.detect_structuring("ent1", amounts)
    assert result is True


@pytest.mark.asyncio
async def test_detect_structuring_sum_just_above_threshold(compliance):
    amounts = [Decimal("5001"), Decimal("5000")]
    result = await compliance.detect_structuring("ent1", amounts)
    assert result is True


@pytest.mark.asyncio
async def test_detect_structuring_empty_list(compliance):
    result = await compliance.detect_structuring("ent1", [])
    assert result is False


@pytest.mark.asyncio
async def test_detect_structuring_sum_below_threshold(compliance):
    amounts = [Decimal("2000"), Decimal("3000")]
    result = await compliance.detect_structuring("ent1", amounts)
    assert result is False
