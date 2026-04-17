"""
tests/test_loyalty/test_cashback_processor.py — Unit tests for CashbackProcessor
IL-LRE-01 | Phase 29 | banxe-emi-stack
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.loyalty.cashback_processor import MCC_RATES, CashbackProcessor


@pytest.fixture()
def processor() -> CashbackProcessor:
    return CashbackProcessor()


# ── MCC_RATES constants ────────────────────────────────────────────────────


def test_mcc_grocery_rate_is_2_pct() -> None:
    assert MCC_RATES["5411"] == Decimal("0.02")


def test_mcc_restaurant_rate_is_3_pct() -> None:
    assert MCC_RATES["5812"] == Decimal("0.03")


def test_mcc_fuel_rate_is_1_pct() -> None:
    assert MCC_RATES["5541"] == Decimal("0.01")


def test_mcc_default_rate_is_0_5_pct() -> None:
    assert MCC_RATES["default"] == Decimal("0.005")


# ── calculate_cashback — pure ──────────────────────────────────────────────


def test_calculate_cashback_grocery(processor: CashbackProcessor) -> None:
    result = processor.calculate_cashback("cust-1", "100.00", "5411")
    assert result["cashback_amount"] == "2.00"


def test_calculate_cashback_restaurant(processor: CashbackProcessor) -> None:
    result = processor.calculate_cashback("cust-1", "100.00", "5812")
    assert result["cashback_amount"] == "3.00"


def test_calculate_cashback_fuel(processor: CashbackProcessor) -> None:
    result = processor.calculate_cashback("cust-1", "100.00", "5541")
    assert result["cashback_amount"] == "1.00"


def test_calculate_cashback_unknown_mcc_uses_default(processor: CashbackProcessor) -> None:
    result = processor.calculate_cashback("cust-1", "100.00", "9999")
    assert result["cashback_amount"] == "0.50"


def test_calculate_cashback_default_mcc(processor: CashbackProcessor) -> None:
    result = processor.calculate_cashback("cust-1", "100.00")
    assert result["cashback_amount"] == "0.50"


def test_calculate_cashback_returns_rate(processor: CashbackProcessor) -> None:
    result = processor.calculate_cashback("cust-1", "100.00", "5411")
    assert result["rate"] == "0.02"


def test_calculate_cashback_returns_mcc(processor: CashbackProcessor) -> None:
    result = processor.calculate_cashback("cust-1", "100.00", "5411")
    assert result["mcc"] == "5411"


def test_calculate_cashback_is_pure_no_side_effects(processor: CashbackProcessor) -> None:
    """calculate_cashback should not modify balance."""
    from services.loyalty.models import InMemoryPointsBalanceStore

    store = InMemoryPointsBalanceStore()
    proc = CashbackProcessor(balance_store=store)
    proc.calculate_cashback("pure-cust", "200.00", "5812")
    # Balance should not be created
    assert store.get("pure-cust") is None


# ── process_cashback ───────────────────────────────────────────────────────


def test_process_cashback_creates_new_customer_balance(processor: CashbackProcessor) -> None:
    result = processor.process_cashback("new-cb-cust", "100.00", "5411")
    assert result["cashback_amount"] == "2.00"
    assert result["new_balance"] != ""


def test_process_cashback_grocery_100_gives_200_points(processor: CashbackProcessor) -> None:
    # 2% of £100 = £2 cashback → 200 points (100 pts/£1)
    result = processor.process_cashback("cb-cust-1", "100.00", "5411")
    assert result["points_earned"] == "200"


def test_process_cashback_restaurant_100_gives_300_points(processor: CashbackProcessor) -> None:
    # 3% of £100 = £3 → 300 points
    result = processor.process_cashback("cb-cust-2", "100.00", "5812")
    assert result["points_earned"] == "300"


def test_process_cashback_default_mcc_100_gives_50_points(processor: CashbackProcessor) -> None:
    # 0.5% of £100 = £0.50 → 50 points
    result = processor.process_cashback("cb-cust-3", "100.00")
    assert result["points_earned"] == "50"


def test_process_cashback_accumulates_balance(processor: CashbackProcessor) -> None:
    processor.process_cashback("acc-cust", "100.00", "5411")
    result = processor.process_cashback("acc-cust", "100.00", "5411")
    assert result["new_balance"] == "400"  # 200 + 200


def test_process_cashback_returns_cashback_amount(processor: CashbackProcessor) -> None:
    result = processor.process_cashback("cb-ret-cust", "200.00", "5812")
    assert result["cashback_amount"] == "6.00"


def test_process_cashback_with_reference_id(processor: CashbackProcessor) -> None:
    result = processor.process_cashback("cb-ref-cust", "50.00", "5411", reference_id="tx-123")
    assert "points_earned" in result


# ── list_mcc_rates ─────────────────────────────────────────────────────────


def test_list_mcc_rates_returns_all(processor: CashbackProcessor) -> None:
    result = processor.list_mcc_rates()
    assert "rates" in result
    assert len(result["rates"]) == len(MCC_RATES)


def test_list_mcc_rates_has_mcc_and_rate_keys(processor: CashbackProcessor) -> None:
    result = processor.list_mcc_rates()
    for entry in result["rates"]:
        assert "mcc" in entry
        assert "rate" in entry
