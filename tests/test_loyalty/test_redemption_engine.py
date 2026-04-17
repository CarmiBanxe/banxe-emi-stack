"""
tests/test_loyalty/test_redemption_engine.py — Unit tests for RedemptionEngine
IL-LRE-01 | Phase 29 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import uuid

import pytest

from services.loyalty.models import (
    InMemoryPointsBalanceStore,
    PointsBalance,
    RewardTier,
)
from services.loyalty.redemption_engine import RedemptionEngine


def _customer_with_balance(
    customer_id: str, points: Decimal
) -> tuple[InMemoryPointsBalanceStore, PointsBalance]:
    store = InMemoryPointsBalanceStore()
    b = PointsBalance(
        balance_id=str(uuid.uuid4()),
        customer_id=customer_id,
        tier=RewardTier.GOLD,
        total_points=points,
        pending_points=Decimal("0"),
        lifetime_points=points,
        updated_at=datetime.now(UTC),
    )
    store.save(b)
    return store, b


@pytest.fixture()
def engine() -> RedemptionEngine:
    return RedemptionEngine()


@pytest.fixture()
def rich_engine() -> RedemptionEngine:
    """Engine with a customer pre-loaded with 10,000 points."""
    store, _ = _customer_with_balance("rich-cust", Decimal("10000"))
    return RedemptionEngine(balance_store=store)


# ── list_options ───────────────────────────────────────────────────────────


def test_list_options_new_customer_cannot_afford_all(engine: RedemptionEngine) -> None:
    result = engine.list_options("broke-cust")
    for opt in result["options"]:
        assert opt["can_afford"] is False


def test_list_options_returns_customer_id(engine: RedemptionEngine) -> None:
    result = engine.list_options("list-cust")
    assert result["customer_id"] == "list-cust"


def test_list_options_returns_current_balance(engine: RedemptionEngine) -> None:
    result = engine.list_options("list-cust-2")
    assert result["current_balance"] == "0"


def test_list_options_with_balance_can_afford_cashback(rich_engine: RedemptionEngine) -> None:
    result = rich_engine.list_options("rich-cust")
    cashback_opts = [o for o in result["options"] if o["option_id"] == "opt-cashback"]
    assert len(cashback_opts) == 1
    assert cashback_opts[0]["can_afford"] is True


def test_list_options_returns_4_options(engine: RedemptionEngine) -> None:
    result = engine.list_options("opts-cust")
    assert len(result["options"]) == 4


def test_list_options_has_can_afford_flag(engine: RedemptionEngine) -> None:
    result = engine.list_options("opts-cust-2")
    for opt in result["options"]:
        assert "can_afford" in opt


# ── redeem ─────────────────────────────────────────────────────────────────


def test_redeem_cashback_success(rich_engine: RedemptionEngine) -> None:
    result = rich_engine.redeem("rich-cust", "opt-cashback")
    assert result["redeemed_points"] == "1000"


def test_redeem_cashback_reduces_balance(rich_engine: RedemptionEngine) -> None:
    result = rich_engine.redeem("rich-cust", "opt-cashback")
    assert result["remaining_balance"] == "9000"


def test_redeem_returns_reward_info(rich_engine: RedemptionEngine) -> None:
    result = rich_engine.redeem("rich-cust", "opt-cashback")
    assert "reward" in result
    assert result["reward"]["type"] == "CASHBACK"


def test_redeem_quantity_2_deducts_double(rich_engine: RedemptionEngine) -> None:
    result = rich_engine.redeem("rich-cust", "opt-cashback", quantity=2)
    assert result["redeemed_points"] == "2000"
    assert result["remaining_balance"] == "8000"


def test_redeem_invalid_option_raises(engine: RedemptionEngine) -> None:
    with pytest.raises(ValueError, match="not found"):
        engine.redeem("any-cust", "opt-nonexistent")


def test_redeem_no_balance_raises(engine: RedemptionEngine) -> None:
    with pytest.raises(ValueError, match="No points balance"):
        engine.redeem("no-balance-cust", "opt-cashback")


def test_redeem_insufficient_balance_raises() -> None:
    store, _ = _customer_with_balance("poor-cust", Decimal("500"))
    engine = RedemptionEngine(balance_store=store)
    with pytest.raises(ValueError, match="Insufficient points"):
        engine.redeem("poor-cust", "opt-cashback")  # requires 1000


def test_redeem_zero_quantity_raises(rich_engine: RedemptionEngine) -> None:
    with pytest.raises(ValueError, match="Quantity must be"):
        rich_engine.redeem("rich-cust", "opt-cashback", quantity=0)


def test_redeem_card_fee_waiver() -> None:
    store, _ = _customer_with_balance("fee-cust", Decimal("3000"))
    engine = RedemptionEngine(balance_store=store)
    result = engine.redeem("fee-cust", "opt-card-fee")
    assert result["redeemed_points"] == "2000"


# ── get_redemption_history ─────────────────────────────────────────────────


def test_redemption_history_empty_new_customer(engine: RedemptionEngine) -> None:
    result = engine.get_redemption_history("history-cust")
    assert result["redemptions"] == []


def test_redemption_history_after_redemption(rich_engine: RedemptionEngine) -> None:
    rich_engine.redeem("rich-cust", "opt-cashback")
    result = rich_engine.get_redemption_history("rich-cust")
    assert len(result["redemptions"]) == 1


def test_redemption_history_returns_customer_id(engine: RedemptionEngine) -> None:
    result = engine.get_redemption_history("h-cust")
    assert result["customer_id"] == "h-cust"
