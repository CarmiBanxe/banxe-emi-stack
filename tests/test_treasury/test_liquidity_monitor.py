"""
tests/test_treasury/test_liquidity_monitor.py
IL-TLM-01 | Phase 17 — LiquidityMonitor tests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.treasury.liquidity_monitor import LiquidityMonitor
from services.treasury.models import (
    InMemoryLiquidityStore,
    InMemoryTreasuryAudit,
    LiquidityPool,
    PoolStatus,
    make_sample_pool,
)

_NOW = datetime.now(UTC)


def _build_monitor(
    pool: LiquidityPool | None = None,
) -> tuple[LiquidityMonitor, InMemoryLiquidityStore, InMemoryTreasuryAudit]:
    store = InMemoryLiquidityStore()
    audit = InMemoryTreasuryAudit()
    monitor = LiquidityMonitor(store, audit)
    return monitor, store, audit


async def _seeded_monitor(
    pool: LiquidityPool | None = None,
) -> tuple[LiquidityMonitor, InMemoryLiquidityStore, InMemoryTreasuryAudit]:
    monitor, store, audit = _build_monitor()
    p = pool or make_sample_pool()
    await store.save_pool(p)
    return monitor, store, audit


@pytest.mark.asyncio
async def test_get_positions_empty_pool() -> None:
    monitor, store, _ = await _seeded_monitor()
    positions = await monitor.get_positions("pool-001")
    assert positions == []


@pytest.mark.asyncio
async def test_get_positions_after_add_returns_one() -> None:
    monitor, store, _ = await _seeded_monitor()
    await monitor.add_position("pool-001", "1000.00", "GBP", "test", True, "actor")
    positions = await monitor.get_positions("pool-001")
    assert len(positions) == 1


@pytest.mark.asyncio
async def test_add_position_amount_parsed_from_string() -> None:
    monitor, _, _ = await _seeded_monitor()
    pos = await monitor.add_position("pool-001", "1000.00", "GBP", "test", True, "actor")
    assert pos.amount == Decimal("1000.00")
    assert isinstance(pos.amount, Decimal)


@pytest.mark.asyncio
async def test_add_position_creates_audit_entry() -> None:
    monitor, _, audit = await _seeded_monitor()
    await monitor.add_position("pool-001", "500.00", "GBP", "audit test", True, "operator")
    events = await audit.list_events("pool-001")
    event_types = [e["event_type"] for e in events]
    assert "liquidity.position_added" in event_types


@pytest.mark.asyncio
async def test_get_pool_summary_has_pool_id_key() -> None:
    monitor, _, _ = await _seeded_monitor()
    summary = await monitor.get_pool_summary("pool-001")
    assert "pool_id" in summary


@pytest.mark.asyncio
async def test_get_pool_summary_surplus_positive_when_balance_exceeds_min() -> None:
    monitor, _, _ = await _seeded_monitor()
    summary = await monitor.get_pool_summary("pool-001")
    assert Decimal(summary["surplus_or_deficit"]) > Decimal("0")


@pytest.mark.asyncio
async def test_get_pool_summary_is_compliant_true() -> None:
    monitor, _, _ = await _seeded_monitor()
    summary = await monitor.get_pool_summary("pool-001")
    assert summary["is_compliant"] is True


@pytest.mark.asyncio
async def test_get_pool_summary_is_compliant_false_when_below_minimum() -> None:
    low_pool = LiquidityPool(
        id="pool-low",
        name="Low Pool",
        currency="GBP",
        current_balance=Decimal("100000"),
        required_minimum=Decimal("500000"),
        status=PoolStatus.ACTIVE,
        aspsp_account_id="aspsp-low",
        updated_at=_NOW,
    )
    monitor, store, _ = _build_monitor()
    await store.save_pool(low_pool)
    summary = await monitor.get_pool_summary("pool-low")
    assert summary["is_compliant"] is False


@pytest.mark.asyncio
async def test_check_compliance_true_for_compliant_pool() -> None:
    monitor, _, _ = await _seeded_monitor()
    assert await monitor.check_compliance("pool-001") is True


@pytest.mark.asyncio
async def test_check_compliance_false_for_pool_below_minimum() -> None:
    monitor, store, _ = _build_monitor()
    low_pool = LiquidityPool(
        id="pool-lo",
        name="Low",
        currency="GBP",
        current_balance=Decimal("10000"),
        required_minimum=Decimal("500000"),
        status=PoolStatus.ACTIVE,
        aspsp_account_id="aspsp-lo",
        updated_at=_NOW,
    )
    await store.save_pool(low_pool)
    assert await monitor.check_compliance("pool-lo") is False


@pytest.mark.asyncio
async def test_get_all_pools_returns_list() -> None:
    monitor, store, _ = _build_monitor()
    await store.save_pool(make_sample_pool("p1"))
    await store.save_pool(make_sample_pool("p2"))
    pools = await monitor.get_all_pools()
    assert len(pools) == 2


@pytest.mark.asyncio
async def test_add_position_with_client_money_true() -> None:
    monitor, _, _ = await _seeded_monitor()
    pos = await monitor.add_position("pool-001", "500.00", "GBP", "client funds", True, "a")
    assert pos.is_client_money is True


@pytest.mark.asyncio
async def test_add_position_with_client_money_false() -> None:
    monitor, _, _ = await _seeded_monitor()
    pos = await monitor.add_position("pool-001", "500.00", "GBP", "own funds", False, "a")
    assert pos.is_client_money is False


@pytest.mark.asyncio
async def test_multiple_positions_for_same_pool() -> None:
    monitor, _, _ = await _seeded_monitor()
    await monitor.add_position("pool-001", "100.00", "GBP", "first", True, "a")
    await monitor.add_position("pool-001", "200.00", "GBP", "second", False, "a")
    positions = await monitor.get_positions("pool-001")
    assert len(positions) == 2


@pytest.mark.asyncio
async def test_get_pool_summary_position_count_correct() -> None:
    monitor, _, _ = await _seeded_monitor()
    await monitor.add_position("pool-001", "100.00", "GBP", "a", True, "a")
    await monitor.add_position("pool-001", "200.00", "GBP", "b", True, "a")
    summary = await monitor.get_pool_summary("pool-001")
    assert summary["position_count"] == 2


@pytest.mark.asyncio
async def test_surplus_or_deficit_castable_to_decimal() -> None:
    monitor, _, _ = await _seeded_monitor()
    summary = await monitor.get_pool_summary("pool-001")
    # Must be castable from string to Decimal without error
    value = Decimal(summary["surplus_or_deficit"])
    assert isinstance(value, Decimal)


@pytest.mark.asyncio
async def test_get_pool_summary_not_found_raises_value_error() -> None:
    monitor, _, _ = _build_monitor()
    with pytest.raises(ValueError):
        await monitor.get_pool_summary("nonexistent-pool")


@pytest.mark.asyncio
async def test_add_position_currency_stored() -> None:
    monitor, _, _ = await _seeded_monitor()
    pos = await monitor.add_position("pool-001", "100.00", "EUR", "fx pos", False, "a")
    assert pos.currency == "EUR"


@pytest.mark.asyncio
async def test_add_position_description_stored() -> None:
    monitor, _, _ = await _seeded_monitor()
    pos = await monitor.add_position("pool-001", "100.00", "GBP", "my description", False, "a")
    assert pos.description == "my description"


@pytest.mark.asyncio
async def test_add_position_id_is_unique() -> None:
    monitor, _, _ = await _seeded_monitor()
    p1 = await monitor.add_position("pool-001", "100.00", "GBP", "a", True, "actor")
    p2 = await monitor.add_position("pool-001", "200.00", "GBP", "b", True, "actor")
    assert p1.id != p2.id


@pytest.mark.asyncio
async def test_get_pool_summary_current_balance_is_string() -> None:
    monitor, _, _ = await _seeded_monitor()
    summary = await monitor.get_pool_summary("pool-001")
    assert isinstance(summary["current_balance"], str)
    # confirm it represents the correct value
    assert Decimal(summary["current_balance"]) == Decimal("2500000")
