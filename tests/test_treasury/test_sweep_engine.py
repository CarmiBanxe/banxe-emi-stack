"""
tests/test_treasury/test_sweep_engine.py
IL-TLM-01 | Phase 17 — SweepEngine tests.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.treasury.models import (
    InMemoryLiquidityStore,
    InMemorySweepStore,
    InMemoryTreasuryAudit,
    SweepDirection,
    make_sample_pool,
)
from services.treasury.sweep_engine import SweepEngine


def _make_engine() -> tuple[
    SweepEngine, InMemoryLiquidityStore, InMemorySweepStore, InMemoryTreasuryAudit
]:
    store = InMemoryLiquidityStore()
    sweep_store = InMemorySweepStore()
    audit = InMemoryTreasuryAudit()
    engine = SweepEngine(store, sweep_store, audit)
    return engine, store, sweep_store, audit


async def _seeded_engine() -> tuple[
    SweepEngine, InMemoryLiquidityStore, InMemorySweepStore, InMemoryTreasuryAudit
]:
    engine, store, sweep_store, audit = _make_engine()
    await store.save_pool(make_sample_pool())
    return engine, store, sweep_store, audit


@pytest.mark.asyncio
async def test_propose_sweep_returns_event_with_no_approval() -> None:
    engine, _, _, _ = await _seeded_engine()
    event = await engine.propose_sweep("pool-001", SweepDirection.SURPLUS_OUT, "100000", "actor")
    assert event.approved_by is None


@pytest.mark.asyncio
async def test_propose_sweep_executed_at_none() -> None:
    engine, _, _, _ = await _seeded_engine()
    event = await engine.propose_sweep("pool-001", SweepDirection.SURPLUS_OUT, "50000", "actor")
    assert event.executed_at is None


@pytest.mark.asyncio
async def test_propose_sweep_amount_parsed_from_string() -> None:
    engine, _, _, _ = await _seeded_engine()
    event = await engine.propose_sweep("pool-001", SweepDirection.SURPLUS_OUT, "12345.67", "actor")
    assert event.amount == Decimal("12345.67")
    assert isinstance(event.amount, Decimal)


@pytest.mark.asyncio
async def test_propose_sweep_creates_audit_entry() -> None:
    engine, _, _, audit = await _seeded_engine()
    await engine.propose_sweep("pool-001", SweepDirection.SURPLUS_OUT, "50000", "operator")
    events = await audit.list_events("pool-001")
    event_types = [e["event_type"] for e in events]
    assert "sweep.proposed" in event_types


@pytest.mark.asyncio
async def test_propose_sweep_pool_not_found_raises_value_error() -> None:
    engine, _, _, _ = _make_engine()
    with pytest.raises(ValueError):
        await engine.propose_sweep("ghost-pool", SweepDirection.SURPLUS_OUT, "1000", "actor")


@pytest.mark.asyncio
async def test_propose_sweep_zero_amount_raises_value_error() -> None:
    engine, _, _, _ = await _seeded_engine()
    with pytest.raises(ValueError):
        await engine.propose_sweep("pool-001", SweepDirection.SURPLUS_OUT, "0", "actor")


@pytest.mark.asyncio
async def test_propose_sweep_negative_amount_raises_value_error() -> None:
    engine, _, _, _ = await _seeded_engine()
    with pytest.raises(ValueError):
        await engine.propose_sweep("pool-001", SweepDirection.SURPLUS_OUT, "-500", "actor")


@pytest.mark.asyncio
async def test_approve_and_execute_sets_approved_by() -> None:
    engine, _, _, _ = await _seeded_engine()
    event = await engine.propose_sweep("pool-001", SweepDirection.SURPLUS_OUT, "10000", "actor")
    approved = await engine.approve_and_execute(event.id, "mlro")
    assert approved.approved_by == "mlro"


@pytest.mark.asyncio
async def test_approve_and_execute_creates_audit_entry() -> None:
    engine, _, _, audit = await _seeded_engine()
    event = await engine.propose_sweep("pool-001", SweepDirection.SURPLUS_OUT, "10000", "actor")
    await engine.approve_and_execute(event.id, "mlro")
    events = await audit.list_events("pool-001")
    event_types = [e["event_type"] for e in events]
    assert "sweep.approved_and_executed" in event_types


@pytest.mark.asyncio
async def test_list_pending_sweeps_returns_unapproved() -> None:
    engine, _, _, _ = await _seeded_engine()
    await engine.propose_sweep("pool-001", SweepDirection.SURPLUS_OUT, "5000", "actor")
    pending = await engine.list_pending_sweeps()
    assert len(pending) == 1
    assert pending[0].approved_by is None


@pytest.mark.asyncio
async def test_list_pending_sweeps_excludes_approved() -> None:
    engine, _, _, _ = await _seeded_engine()
    event = await engine.propose_sweep("pool-001", SweepDirection.SURPLUS_OUT, "5000", "actor")
    await engine.approve_and_execute(event.id, "mlro")
    pending = await engine.list_pending_sweeps()
    assert len(pending) == 0


@pytest.mark.asyncio
async def test_list_all_sweeps_includes_approved() -> None:
    engine, _, _, _ = await _seeded_engine()
    event = await engine.propose_sweep("pool-001", SweepDirection.SURPLUS_OUT, "5000", "actor")
    await engine.approve_and_execute(event.id, "mlro")
    all_sweeps = await engine.list_all_sweeps()
    assert len(all_sweeps) == 1


@pytest.mark.asyncio
async def test_propose_sweep_surplus_out_direction() -> None:
    engine, _, _, _ = await _seeded_engine()
    event = await engine.propose_sweep("pool-001", SweepDirection.SURPLUS_OUT, "1000", "actor")
    assert event.direction == SweepDirection.SURPLUS_OUT


@pytest.mark.asyncio
async def test_propose_sweep_deficit_in_direction() -> None:
    engine, _, _, _ = await _seeded_engine()
    event = await engine.propose_sweep("pool-001", SweepDirection.DEFICIT_IN, "1000", "actor")
    assert event.direction == SweepDirection.DEFICIT_IN


@pytest.mark.asyncio
async def test_multiple_sweeps_for_same_pool() -> None:
    engine, _, _, _ = await _seeded_engine()
    await engine.propose_sweep("pool-001", SweepDirection.SURPLUS_OUT, "1000", "actor")
    await engine.propose_sweep("pool-001", SweepDirection.SURPLUS_OUT, "2000", "actor")
    all_sweeps = await engine.list_all_sweeps("pool-001")
    assert len(all_sweeps) == 2


@pytest.mark.asyncio
async def test_list_pending_sweeps_filter_by_pool_id() -> None:
    engine, store, _, _ = _make_engine()
    await store.save_pool(make_sample_pool("pool-A"))
    await store.save_pool(make_sample_pool("pool-B"))
    await engine.propose_sweep("pool-A", SweepDirection.SURPLUS_OUT, "1000", "actor")
    await engine.propose_sweep("pool-B", SweepDirection.SURPLUS_OUT, "2000", "actor")
    pending_a = await engine.list_pending_sweeps("pool-A")
    assert len(pending_a) == 1
    assert pending_a[0].pool_id == "pool-A"


@pytest.mark.asyncio
async def test_propose_sweep_description_stored() -> None:
    engine, _, _, _ = await _seeded_engine()
    event = await engine.propose_sweep(
        "pool-001", SweepDirection.SURPLUS_OUT, "5000", "actor", description="Quarterly sweep"
    )
    assert event.description == "Quarterly sweep"


@pytest.mark.asyncio
async def test_approve_nonexistent_sweep_raises_key_error() -> None:
    engine, _, _, _ = await _seeded_engine()
    with pytest.raises(KeyError):
        await engine.approve_and_execute("nonexistent-id", "mlro")


@pytest.mark.asyncio
async def test_list_pending_sweeps_empty_initially() -> None:
    engine, _, _, _ = await _seeded_engine()
    pending = await engine.list_pending_sweeps()
    assert pending == []


@pytest.mark.asyncio
async def test_propose_sweep_currency_matches_pool() -> None:
    engine, _, _, _ = await _seeded_engine()
    event = await engine.propose_sweep("pool-001", SweepDirection.SURPLUS_OUT, "5000", "actor")
    assert event.currency == "GBP"


@pytest.mark.asyncio
async def test_approve_and_execute_sets_executed_at() -> None:
    engine, _, _, _ = await _seeded_engine()
    event = await engine.propose_sweep("pool-001", SweepDirection.DEFICIT_IN, "5000", "actor")
    approved = await engine.approve_and_execute(event.id, "mlro")
    assert approved.executed_at is not None
