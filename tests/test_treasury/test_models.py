"""
tests/test_treasury/test_models.py
IL-TLM-01 | Phase 17 — Domain model and InMemory stub tests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.treasury.models import (
    CashPosition,
    ForecastHorizon,
    ForecastResult,
    FundingSource,
    FundingSourceType,
    InMemoryForecastStore,
    InMemoryLiquidityStore,
    InMemoryReconciliationStore,
    InMemorySweepStore,
    InMemoryTreasuryAudit,
    LiquidityPool,
    PoolStatus,
    ReconciliationRecord,
    ReconciliationStatus,
    SafeguardingAccount,
    SweepDirection,
    SweepEvent,
    make_sample_pool,
)

_NOW = datetime.now(UTC)


def _pool(
    pool_id: str = "pool-001", balance: str = "2500000", minimum: str = "500000"
) -> LiquidityPool:
    return LiquidityPool(
        id=pool_id,
        name="Test Pool",
        currency="GBP",
        current_balance=Decimal(balance),
        required_minimum=Decimal(minimum),
        status=PoolStatus.ACTIVE,
        aspsp_account_id="aspsp-001",
        updated_at=_NOW,
    )


def _position(pool_id: str = "pool-001") -> CashPosition:
    return CashPosition(
        id="pos-001",
        pool_id=pool_id,
        amount=Decimal("10000"),
        currency="GBP",
        value_date=_NOW,
        description="Test position",
        is_client_money=True,
    )


def _forecast(pool_id: str = "pool-001") -> ForecastResult:
    return ForecastResult(
        id="fc-001",
        pool_id=pool_id,
        horizon=ForecastHorizon.DAYS_7,
        forecast_amount=Decimal("2000000"),
        confidence=Decimal("0.75"),
        generated_at=_NOW,
        model_version="v1",
        shortfall_risk=False,
    )


def _sweep(pool_id: str = "pool-001") -> SweepEvent:
    return SweepEvent(
        id="sweep-001",
        pool_id=pool_id,
        direction=SweepDirection.SURPLUS_OUT,
        amount=Decimal("100000"),
        currency="GBP",
        executed_at=None,
        proposed_at=_NOW,
        approved_by=None,
        description="Test sweep",
    )


def _recon_record(account_id: str = "acc-001") -> ReconciliationRecord:
    return ReconciliationRecord(
        id="recon-001",
        account_id=account_id,
        period_date=_NOW,
        book_balance=Decimal("1000"),
        bank_balance=Decimal("1000"),
        variance=Decimal("0"),
        status=ReconciliationStatus.MATCHED,
        reconciled_at=_NOW,
        notes="OK",
    )


# ── Dataclass tests ───────────────────────────────────────────────────────────


def test_liquidity_pool_frozen() -> None:
    pool = _pool()
    with pytest.raises(AttributeError):
        pool.name = "new name"  # type: ignore[misc]


def test_liquidity_pool_balance_is_decimal() -> None:
    pool = _pool()
    assert isinstance(pool.current_balance, Decimal)


def test_cash_position_client_money_flag() -> None:
    pos = _position()
    assert pos.is_client_money is True


def test_cash_position_not_client_money() -> None:
    pos = CashPosition(
        id="p2",
        pool_id="pool-001",
        amount=Decimal("5000"),
        currency="GBP",
        value_date=_NOW,
        description="Own funds",
        is_client_money=False,
    )
    assert pos.is_client_money is False


def test_funding_source_interest_rate_is_decimal() -> None:
    fs = FundingSource(
        id="fs-001",
        name="Barclays Credit",
        source_type=FundingSourceType.CREDIT_LINE,
        available_amount=Decimal("500000"),
        drawn_amount=Decimal("0"),
        interest_rate=Decimal("0.0475"),
        currency="GBP",
        maturity_date=None,
    )
    assert isinstance(fs.interest_rate, Decimal)


def test_safeguarding_account_balances_are_decimal() -> None:
    acct = SafeguardingAccount(
        id="acc-001",
        institution="Barclays",
        iban="GB12BARC20201512345678",
        balance=Decimal("100000"),
        client_money_held=Decimal("95000"),
        currency="GBP",
        last_reconciled_at=_NOW,
    )
    assert isinstance(acct.balance, Decimal)
    assert isinstance(acct.client_money_held, Decimal)


def test_forecast_result_confidence_is_decimal() -> None:
    fc = _forecast()
    assert isinstance(fc.confidence, Decimal)


def test_sweep_event_executed_at_none() -> None:
    sw = _sweep()
    assert sw.executed_at is None


def test_recon_record_variance_equals_book_minus_bank() -> None:
    book = Decimal("1001")
    bank = Decimal("1000")
    rec = ReconciliationRecord(
        id="r1",
        account_id="acc-001",
        period_date=_NOW,
        book_balance=book,
        bank_balance=bank,
        variance=book - bank,
        status=ReconciliationStatus.DISCREPANCY,
        reconciled_at=_NOW,
        notes="delta",
    )
    assert rec.variance == Decimal("1")


def test_pool_status_enum_values() -> None:
    assert PoolStatus.ACTIVE.value == "ACTIVE"
    assert PoolStatus.SUSPENDED.value == "SUSPENDED"
    assert PoolStatus.CLOSED.value == "CLOSED"


def test_sweep_direction_enum_values() -> None:
    assert SweepDirection.SURPLUS_OUT.value == "SURPLUS_OUT"
    assert SweepDirection.DEFICIT_IN.value == "DEFICIT_IN"


def test_make_sample_pool_returns_valid_pool() -> None:
    pool = make_sample_pool()
    assert pool.id == "pool-001"
    assert pool.currency == "GBP"
    assert pool.current_balance == Decimal("2500000")
    assert pool.required_minimum == Decimal("500000")


def test_make_sample_pool_custom_id() -> None:
    pool = make_sample_pool("pool-xyz")
    assert pool.id == "pool-xyz"


# ── InMemory store tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_inmemory_liquidity_store_save_get() -> None:
    store = InMemoryLiquidityStore()
    pool = _pool()
    await store.save_pool(pool)
    fetched = await store.get_pool("pool-001")
    assert fetched is not None
    assert fetched.id == "pool-001"


@pytest.mark.asyncio
async def test_inmemory_liquidity_store_list_pools() -> None:
    store = InMemoryLiquidityStore()
    await store.save_pool(_pool("p1"))
    await store.save_pool(_pool("p2"))
    pools = await store.list_pools()
    assert len(pools) == 2


@pytest.mark.asyncio
async def test_inmemory_liquidity_store_add_list_positions() -> None:
    store = InMemoryLiquidityStore()
    await store.save_pool(_pool())
    pos = _position()
    await store.add_position(pos)
    positions = await store.list_positions("pool-001")
    assert len(positions) == 1


@pytest.mark.asyncio
async def test_inmemory_liquidity_store_positions_filter() -> None:
    store = InMemoryLiquidityStore()
    await store.save_pool(_pool("p1"))
    await store.save_pool(_pool("p2"))
    await store.add_position(_position("p1"))
    await store.add_position(_position("p2"))
    assert len(await store.list_positions("p1")) == 1
    assert len(await store.list_positions("p2")) == 1


@pytest.mark.asyncio
async def test_inmemory_forecast_store_save_get_latest() -> None:
    store = InMemoryForecastStore()
    fc = _forecast()
    await store.save_forecast(fc)
    latest = await store.get_latest("pool-001", ForecastHorizon.DAYS_7)
    assert latest is not None
    assert latest.id == "fc-001"


@pytest.mark.asyncio
async def test_inmemory_forecast_store_list() -> None:
    store = InMemoryForecastStore()
    await store.save_forecast(_forecast())
    results = await store.list_forecasts("pool-001")
    assert len(results) == 1


@pytest.mark.asyncio
async def test_inmemory_sweep_store_save_list() -> None:
    store = InMemorySweepStore()
    sw = _sweep()
    await store.save_sweep(sw)
    sweeps = await store.list_sweeps()
    assert len(sweeps) == 1


@pytest.mark.asyncio
async def test_inmemory_sweep_store_approve() -> None:
    store = InMemorySweepStore()
    sw = _sweep()
    await store.save_sweep(sw)
    approved = await store.approve_sweep("sweep-001", "alice")
    assert approved.approved_by == "alice"
    assert approved.executed_at is not None


@pytest.mark.asyncio
async def test_inmemory_recon_store_save_list() -> None:
    store = InMemoryReconciliationStore()
    rec = _recon_record()
    await store.save_record(rec)
    records = await store.list_records()
    assert len(records) == 1


@pytest.mark.asyncio
async def test_inmemory_recon_store_get_latest() -> None:
    store = InMemoryReconciliationStore()
    await store.save_record(_recon_record())
    latest = await store.get_latest("acc-001")
    assert latest is not None


@pytest.mark.asyncio
async def test_inmemory_audit_log_list_events() -> None:
    audit = InMemoryTreasuryAudit()
    await audit.log("test.event", "entity-1", {"k": "v"}, "actor")
    events = await audit.list_events()
    assert len(events) == 1


@pytest.mark.asyncio
async def test_inmemory_audit_filter_by_entity() -> None:
    audit = InMemoryTreasuryAudit()
    await audit.log("event.a", "entity-1", {}, "actor")
    await audit.log("event.b", "entity-2", {}, "actor")
    events = await audit.list_events("entity-1")
    assert len(events) == 1
    assert events[0]["entity_id"] == "entity-1"
