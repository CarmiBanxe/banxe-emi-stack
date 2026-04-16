"""tests/test_fx_exchange/test_fx_executor.py — FXExecutor tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.fx_exchange.fx_executor import _FX_FEE_RATE, FXExecutor
from services.fx_exchange.models import (
    ComplianceFlag,
    CurrencyPair,
    FXOrderStatus,
    FXQuote,
    InMemoryExecutionStore,
    InMemoryFXAudit,
    InMemoryOrderStore,
    RateSource,
)


def _make_quote(
    pair: CurrencyPair = CurrencyPair("GBP", "EUR"),
    rate: Decimal = Decimal("1.17"),
) -> FXQuote:
    now = datetime.now(UTC)
    return FXQuote(
        quote_id="q-test",
        pair=pair,
        rate=rate,
        bid=Decimal("1.169"),
        ask=Decimal("1.171"),
        spread_bps=20,
        source=RateSource.ECB,
        valid_until=now,
        created_at=now,
    )


def _make_executor() -> FXExecutor:
    return FXExecutor(
        order_store=InMemoryOrderStore(),
        execution_store=InMemoryExecutionStore(),
        audit=InMemoryFXAudit(),
    )


@pytest.mark.asyncio
async def test_create_order_returns_pending():
    executor = _make_executor()
    quote = _make_quote()
    order = await executor.create_order(
        "ent1", quote.pair, Decimal("1000"), quote, ComplianceFlag.CLEAR
    )
    assert order.status == FXOrderStatus.PENDING


@pytest.mark.asyncio
async def test_create_order_calculates_amount_quote():
    executor = _make_executor()
    quote = _make_quote(rate=Decimal("1.17"))
    order = await executor.create_order(
        "ent1", quote.pair, Decimal("1000"), quote, ComplianceFlag.CLEAR
    )
    assert order.amount_quote == Decimal("1170")


@pytest.mark.asyncio
async def test_create_order_stores_in_order_store():
    executor = _make_executor()
    quote = _make_quote()
    order = await executor.create_order(
        "ent1", quote.pair, Decimal("1000"), quote, ComplianceFlag.CLEAR
    )
    retrieved = await executor.get_order(order.order_id)
    assert retrieved is not None
    assert retrieved.order_id == order.order_id


@pytest.mark.asyncio
async def test_create_order_blocked_raises_value_error():
    executor = _make_executor()
    quote = _make_quote(pair=CurrencyPair("GBP", "RUB"), rate=Decimal("110"))
    with pytest.raises(ValueError, match="blocked"):
        await executor.create_order(
            "ent1", quote.pair, Decimal("100"), quote, ComplianceFlag.BLOCKED
        )


@pytest.mark.asyncio
async def test_create_order_amount_base_is_decimal():
    executor = _make_executor()
    quote = _make_quote()
    order = await executor.create_order(
        "ent1", quote.pair, Decimal("500"), quote, ComplianceFlag.CLEAR
    )
    assert isinstance(order.amount_base, Decimal)
    assert isinstance(order.amount_quote, Decimal)


@pytest.mark.asyncio
async def test_create_order_edd_required_succeeds():
    executor = _make_executor()
    quote = _make_quote()
    order = await executor.create_order(
        "ent1", quote.pair, Decimal("15000"), quote, ComplianceFlag.EDD_REQUIRED
    )
    assert order.compliance_flag == ComplianceFlag.EDD_REQUIRED
    assert order.status == FXOrderStatus.PENDING


@pytest.mark.asyncio
async def test_execute_order_transitions_to_executed():
    executor = _make_executor()
    quote = _make_quote()
    order = await executor.create_order(
        "ent1", quote.pair, Decimal("1000"), quote, ComplianceFlag.CLEAR
    )
    execution = await executor.execute_order(order.order_id)
    updated_order = await executor.get_order(order.order_id)
    assert updated_order is not None
    assert updated_order.status == FXOrderStatus.EXECUTED


@pytest.mark.asyncio
async def test_execute_order_fee_is_zero_point_one_percent():
    executor = _make_executor()
    quote = _make_quote()
    amount = Decimal("1000")
    order = await executor.create_order("ent1", quote.pair, amount, quote, ComplianceFlag.CLEAR)
    execution = await executor.execute_order(order.order_id)
    expected_fee = amount * _FX_FEE_RATE
    assert execution.fee == expected_fee


@pytest.mark.asyncio
async def test_execute_order_fee_is_decimal():
    executor = _make_executor()
    quote = _make_quote()
    order = await executor.create_order(
        "ent1", quote.pair, Decimal("2000"), quote, ComplianceFlag.CLEAR
    )
    execution = await executor.execute_order(order.order_id)
    assert isinstance(execution.fee, Decimal)


@pytest.mark.asyncio
async def test_execute_order_debit_credit_accounts():
    executor = _make_executor()
    quote = _make_quote(pair=CurrencyPair("GBP", "EUR"))
    order = await executor.create_order(
        "ent1", quote.pair, Decimal("1000"), quote, ComplianceFlag.CLEAR
    )
    execution = await executor.execute_order(order.order_id)
    assert execution.debit_account == "ent1_GBP"
    assert execution.credit_account == "ent1_EUR"


@pytest.mark.asyncio
async def test_execute_order_not_found_raises():
    executor = _make_executor()
    with pytest.raises(ValueError, match="not found"):
        await executor.execute_order("nonexistent-order-id")


@pytest.mark.asyncio
async def test_execute_order_already_executed_raises():
    executor = _make_executor()
    quote = _make_quote()
    order = await executor.create_order(
        "ent1", quote.pair, Decimal("1000"), quote, ComplianceFlag.CLEAR
    )
    await executor.execute_order(order.order_id)
    with pytest.raises(ValueError, match="cannot be executed"):
        await executor.execute_order(order.order_id)


@pytest.mark.asyncio
async def test_get_order_nonexistent_returns_none():
    executor = _make_executor()
    result = await executor.get_order("does-not-exist")
    assert result is None


@pytest.mark.asyncio
async def test_list_executions_for_entity():
    executor = _make_executor()
    quote = _make_quote()
    order = await executor.create_order(
        "ent-list", quote.pair, Decimal("500"), quote, ComplianceFlag.CLEAR
    )
    await executor.execute_order(order.order_id)
    executions = await executor.list_executions("ent-list")
    assert len(executions) == 1


@pytest.mark.asyncio
async def test_list_executions_filters_by_entity():
    executor = _make_executor()
    quote1 = _make_quote()
    quote2 = FXQuote(
        quote_id="q-other",
        pair=CurrencyPair("GBP", "EUR"),
        rate=Decimal("1.17"),
        bid=Decimal("1.169"),
        ask=Decimal("1.171"),
        spread_bps=20,
        source=RateSource.ECB,
        valid_until=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    order1 = await executor.create_order(
        "ent-a", quote1.pair, Decimal("500"), quote1, ComplianceFlag.CLEAR
    )
    order2 = await executor.create_order(
        "ent-b", quote2.pair, Decimal("500"), quote2, ComplianceFlag.CLEAR
    )
    await executor.execute_order(order1.order_id)
    await executor.execute_order(order2.order_id)
    executions_a = await executor.list_executions("ent-a")
    assert len(executions_a) == 1
    assert executions_a[0].debit_account.startswith("ent-a")


@pytest.mark.asyncio
async def test_execute_order_sets_executed_at():
    executor = _make_executor()
    quote = _make_quote()
    order = await executor.create_order(
        "ent1", quote.pair, Decimal("1000"), quote, ComplianceFlag.CLEAR
    )
    await executor.execute_order(order.order_id)
    updated = await executor.get_order(order.order_id)
    assert updated is not None
    assert updated.executed_at is not None
