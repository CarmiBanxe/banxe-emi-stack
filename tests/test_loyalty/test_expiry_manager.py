"""
tests/test_loyalty/test_expiry_manager.py — Unit tests for ExpiryManager
IL-LRE-01 | Phase 29 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import uuid

import pytest

from services.loyalty.expiry_manager import ExpiryManager
from services.loyalty.models import (
    InMemoryPointsBalanceStore,
    InMemoryPointsTransactionStore,
    PointsBalance,
    PointsTransaction,
    PointsTransactionType,
    RewardTier,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _make_balance(
    store: InMemoryPointsBalanceStore,
    customer_id: str,
    points: Decimal,
) -> PointsBalance:
    b = PointsBalance(
        balance_id=str(uuid.uuid4()),
        customer_id=customer_id,
        tier=RewardTier.BRONZE,
        total_points=points,
        pending_points=Decimal("0"),
        lifetime_points=points,
        updated_at=_now(),
    )
    store.save(b)
    return b


def _make_earn_tx(
    tx_store: InMemoryPointsTransactionStore,
    customer_id: str,
    points: Decimal,
    expires_at: datetime,
) -> PointsTransaction:
    tx = PointsTransaction(
        tx_id=str(uuid.uuid4()),
        customer_id=customer_id,
        tx_type=PointsTransactionType.EARN,
        points=points,
        balance_after=points,
        reference_id="",
        description="test earn",
        created_at=_now(),
        expires_at=expires_at,
    )
    tx_store.append(tx)
    return tx


@pytest.fixture()
def manager() -> ExpiryManager:
    return ExpiryManager()


# ── get_expiring_soon ──────────────────────────────────────────────────────


def test_get_expiring_soon_empty_for_new_customer(manager: ExpiryManager) -> None:
    result = manager.get_expiring_soon("new-cust")
    assert result["expiring_transactions"] == []
    assert result["total_expiring_points"] == "0"


def test_get_expiring_soon_returns_customer_id(manager: ExpiryManager) -> None:
    result = manager.get_expiring_soon("soon-cust")
    assert result["customer_id"] == "soon-cust"


def test_get_expiring_soon_returns_days_ahead(manager: ExpiryManager) -> None:
    result = manager.get_expiring_soon("soon-cust-2", days_ahead=14)
    assert result["days_ahead"] == 14


def test_get_expiring_soon_finds_transaction_expiring_in_7_days() -> None:
    tx_store = InMemoryPointsTransactionStore()
    balance_store = InMemoryPointsBalanceStore()
    mgr = ExpiryManager(tx_store=tx_store, balance_store=balance_store)
    now = _now()
    _make_earn_tx(tx_store, "expiry-cust", Decimal("100"), now + timedelta(days=5))
    result = mgr.get_expiring_soon("expiry-cust", days_ahead=7)
    assert len(result["expiring_transactions"]) == 1
    assert result["total_expiring_points"] == "100"


def test_get_expiring_soon_excludes_far_future_transactions() -> None:
    tx_store = InMemoryPointsTransactionStore()
    balance_store = InMemoryPointsBalanceStore()
    mgr = ExpiryManager(tx_store=tx_store, balance_store=balance_store)
    now = _now()
    _make_earn_tx(tx_store, "future-cust", Decimal("200"), now + timedelta(days=60))
    result = mgr.get_expiring_soon("future-cust", days_ahead=30)
    assert result["expiring_transactions"] == []


# ── expire_points ──────────────────────────────────────────────────────────


def test_expire_points_no_overdue_returns_zero(manager: ExpiryManager) -> None:
    result = manager.expire_points("no-expire-cust")
    assert result["expired_points"] == "0"
    assert result["transactions_processed"] == 0


def test_expire_points_no_balance_returns_zero() -> None:
    tx_store = InMemoryPointsTransactionStore()
    balance_store = InMemoryPointsBalanceStore()
    mgr = ExpiryManager(tx_store=tx_store, balance_store=balance_store)
    now = _now()
    _make_earn_tx(tx_store, "no-bal-cust", Decimal("100"), now - timedelta(days=1))
    result = mgr.expire_points("no-bal-cust")
    # No balance record → returns zero
    assert result["expired_points"] == "0"


def test_expire_points_processes_overdue_transactions() -> None:
    tx_store = InMemoryPointsTransactionStore()
    balance_store = InMemoryPointsBalanceStore()
    _make_balance(balance_store, "exp-cust", Decimal("500"))
    mgr = ExpiryManager(tx_store=tx_store, balance_store=balance_store)
    now = _now()
    _make_earn_tx(tx_store, "exp-cust", Decimal("100"), now - timedelta(days=1))
    result = mgr.expire_points("exp-cust")
    assert result["expired_points"] == "100"
    assert result["transactions_processed"] == 1


def test_expire_points_deducts_from_balance() -> None:
    tx_store = InMemoryPointsTransactionStore()
    balance_store = InMemoryPointsBalanceStore()
    _make_balance(balance_store, "deduct-cust", Decimal("500"))
    mgr = ExpiryManager(tx_store=tx_store, balance_store=balance_store)
    now = _now()
    _make_earn_tx(tx_store, "deduct-cust", Decimal("100"), now - timedelta(days=1))
    mgr.expire_points("deduct-cust")
    updated = balance_store.get("deduct-cust")
    assert updated.total_points == Decimal("400")


def test_expire_points_balance_never_goes_below_zero() -> None:
    tx_store = InMemoryPointsTransactionStore()
    balance_store = InMemoryPointsBalanceStore()
    _make_balance(balance_store, "floor-cust", Decimal("50"))
    mgr = ExpiryManager(tx_store=tx_store, balance_store=balance_store)
    now = _now()
    _make_earn_tx(tx_store, "floor-cust", Decimal("200"), now - timedelta(days=1))
    mgr.expire_points("floor-cust")
    updated = balance_store.get("floor-cust")
    assert updated.total_points == Decimal("0")


# ── extend_expiry ──────────────────────────────────────────────────────────


def test_extend_expiry_success() -> None:
    tx_store = InMemoryPointsTransactionStore()
    balance_store = InMemoryPointsBalanceStore()
    _make_balance(balance_store, "ext-cust", Decimal("100"))
    mgr = ExpiryManager(tx_store=tx_store, balance_store=balance_store)
    now = _now()
    tx = _make_earn_tx(tx_store, "ext-cust", Decimal("100"), now + timedelta(days=30))
    result = mgr.extend_expiry("ext-cust", tx.tx_id, extension_days=90)
    assert result["extension_days"] == 90
    assert "new_expires_at" in result


def test_extend_expiry_over_365_returns_hitl(manager: ExpiryManager) -> None:
    result = manager.extend_expiry("any-cust", "any-tx-id", extension_days=366)
    assert result["status"] == "HITL_REQUIRED"


def test_extend_expiry_exactly_365_is_allowed() -> None:
    tx_store = InMemoryPointsTransactionStore()
    balance_store = InMemoryPointsBalanceStore()
    _make_balance(balance_store, "edge-cust", Decimal("100"))
    mgr = ExpiryManager(tx_store=tx_store, balance_store=balance_store)
    now = _now()
    tx = _make_earn_tx(tx_store, "edge-cust", Decimal("100"), now + timedelta(days=30))
    result = mgr.extend_expiry("edge-cust", tx.tx_id, extension_days=365)
    assert "new_expires_at" in result
    assert result.get("status") != "HITL_REQUIRED"


def test_extend_expiry_missing_tx_raises() -> None:
    tx_store = InMemoryPointsTransactionStore()
    balance_store = InMemoryPointsBalanceStore()
    mgr = ExpiryManager(tx_store=tx_store, balance_store=balance_store)
    with pytest.raises(ValueError, match="Transaction not found"):
        mgr.extend_expiry("cust", "nonexistent-tx", extension_days=30)
