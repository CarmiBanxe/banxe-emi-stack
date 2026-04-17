"""
tests/test_crypto_custody/test_fee_calculator.py — Tests for FeeCalculator
IL-CDC-01 | Phase 35 | 16 tests
I-01: All amounts Decimal.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.crypto_custody.fee_calculator import WITHDRAWAL_FEE_PCT, FeeCalculator
from services.crypto_custody.models import AssetType, NetworkType


@pytest.fixture()
def calc():
    return FeeCalculator()


def test_withdrawal_fee_pct_is_0_1_percent(calc):
    assert Decimal("0.001") == WITHDRAWAL_FEE_PCT


def test_estimate_network_fee_btc_mainnet(calc):
    fee = calc.estimate_network_fee(AssetType.BTC, NetworkType.MAINNET)
    assert fee == Decimal("0.00010000")


def test_estimate_network_fee_eth_mainnet(calc):
    fee = calc.estimate_network_fee(AssetType.ETH, NetworkType.MAINNET)
    assert fee == Decimal("0.00200000")


def test_estimate_network_fee_testnet_higher(calc):
    mainnet = calc.estimate_network_fee(AssetType.BTC, NetworkType.MAINNET)
    testnet = calc.estimate_network_fee(AssetType.BTC, NetworkType.TESTNET)
    assert testnet > mainnet


def test_estimate_network_fee_returns_decimal(calc):
    fee = calc.estimate_network_fee(AssetType.ETH, NetworkType.MAINNET)
    assert type(fee) is Decimal


def test_calculate_withdrawal_fee_0_1_pct(calc):
    fee = calc.calculate_withdrawal_fee(Decimal("1000"))
    assert fee == Decimal("1")


def test_calculate_withdrawal_fee_small_amount(calc):
    fee = calc.calculate_withdrawal_fee(Decimal("0.001"))
    assert fee == Decimal("0.000001").quantize(Decimal("0.00000001"))


def test_calculate_withdrawal_fee_returns_decimal(calc):
    fee = calc.calculate_withdrawal_fee(Decimal("500"))
    assert type(fee) is Decimal


def test_get_total_fee_has_all_fields(calc):
    est = calc.get_total_fee(Decimal("1"), AssetType.BTC, NetworkType.MAINNET)
    assert est.network_fee > Decimal("0")
    assert est.withdrawal_fee >= Decimal("0")
    assert est.total_fee == est.network_fee + est.withdrawal_fee


def test_get_total_fee_currency_matches_asset(calc):
    est = calc.get_total_fee(Decimal("1"), AssetType.ETH, NetworkType.MAINNET)
    assert est.currency == "ETH"


def test_validate_min_amount_btc_pass(calc):
    assert calc.validate_min_amount(Decimal("0.001"), AssetType.BTC) is True


def test_validate_min_amount_btc_fail(calc):
    assert calc.validate_min_amount(Decimal("0.000001"), AssetType.BTC) is False


def test_validate_max_amount_btc_at_limit(calc):
    assert calc.validate_max_amount(Decimal("10"), AssetType.BTC) is True


def test_validate_max_amount_btc_exceeds(calc):
    assert calc.validate_max_amount(Decimal("10.00000001"), AssetType.BTC) is False


def test_validate_max_amount_eth_at_limit(calc):
    assert calc.validate_max_amount(Decimal("100"), AssetType.ETH) is True


def test_validate_max_amount_usdt_stablecoin_limit(calc):
    assert calc.validate_max_amount(Decimal("1000000"), AssetType.USDT) is True
    assert calc.validate_max_amount(Decimal("1000001"), AssetType.USDT) is False
