"""
tests/test_savings/test_rate_manager.py — Unit tests for RateManager
IL-SIE-01 | Phase 31 | banxe-emi-stack
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.savings.rate_manager import RateManager


@pytest.fixture()
def manager() -> RateManager:
    return RateManager()


# ── set_rate (always HITL) ──────────────────────────────────────────────────────


def test_set_rate_always_returns_hitl_required(manager: RateManager) -> None:
    result = manager.set_rate("prod-easy-access", Decimal("0.05"))
    assert result["status"] == "HITL_REQUIRED"


def test_set_rate_returns_proposed_rate(manager: RateManager) -> None:
    result = manager.set_rate("prod-easy-access", Decimal("0.05"))
    assert result["proposed_rate"] == "0.05"


def test_set_rate_returns_product_id(manager: RateManager) -> None:
    result = manager.set_rate("prod-fixed-12m", Decimal("0.055"))
    assert result["product_id"] == "prod-fixed-12m"


# ── apply_rate_change ──────────────────────────────────────────────────────────


def test_apply_rate_change_saves_rate(manager: RateManager) -> None:
    result = manager.apply_rate_change("prod-easy-access", Decimal("0.05"), Decimal("0.051"))
    assert result["rate_id"] != ""


def test_apply_rate_change_returns_gross_rate(manager: RateManager) -> None:
    result = manager.apply_rate_change("prod-easy-access", Decimal("0.05"), Decimal("0.051"))
    assert result["gross_rate"] == "0.05"


# ── get_current_rate ───────────────────────────────────────────────────────────


def test_get_current_rate_returns_product_default(manager: RateManager) -> None:
    result = manager.get_current_rate("prod-easy-access")
    assert result["source"] == "product_default"
    assert result["gross_rate"] == "0.043"


def test_get_current_rate_returns_store_rate_after_change(manager: RateManager) -> None:
    manager.apply_rate_change("prod-easy-access", Decimal("0.06"), Decimal("0.061"))
    result = manager.get_current_rate("prod-easy-access")
    assert result["source"] == "rate_store"
    assert result["gross_rate"] == "0.06"


def test_get_current_rate_unknown_product_raises(manager: RateManager) -> None:
    with pytest.raises(ValueError, match="Product not found"):
        manager.get_current_rate("nonexistent-product")


# ── get_rate_history ───────────────────────────────────────────────────────────


def test_get_rate_history_empty_initially(manager: RateManager) -> None:
    result = manager.get_rate_history("prod-easy-access")
    assert result["count"] == 0


def test_get_rate_history_after_change(manager: RateManager) -> None:
    manager.apply_rate_change("prod-fixed-12m", Decimal("0.055"), Decimal("0.056"))
    result = manager.get_rate_history("prod-fixed-12m")
    assert result["count"] >= 1


# ── get_tiered_rate ────────────────────────────────────────────────────────────


def test_tiered_rate_below_10k_no_bonus(manager: RateManager) -> None:
    result = manager.get_tiered_rate("prod-easy-access", Decimal("9999.99"))
    assert result["balance_bonus"] == "0"


def test_tiered_rate_above_50k_has_bonus(manager: RateManager) -> None:
    result = manager.get_tiered_rate("prod-easy-access", Decimal("50000.00"))
    assert result["balance_bonus"] == "0.002"


def test_tiered_rate_above_100k_has_max_bonus(manager: RateManager) -> None:
    result = manager.get_tiered_rate("prod-easy-access", Decimal("100000.00"))
    assert result["balance_bonus"] == "0.003"


def test_tiered_rate_effective_rate_includes_bonus(manager: RateManager) -> None:
    result = manager.get_tiered_rate("prod-easy-access", Decimal("50000.00"))
    base = Decimal(result["base_rate"])
    bonus = Decimal(result["balance_bonus"])
    effective = Decimal(result["effective_rate"])
    assert effective == base + bonus
