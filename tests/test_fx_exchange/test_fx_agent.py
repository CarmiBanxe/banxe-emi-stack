"""tests/test_fx_exchange/test_fx_agent.py — FXAgent integration tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.fx_exchange.fx_agent import FXAgent
from services.fx_exchange.fx_compliance import FXCompliance
from services.fx_exchange.fx_executor import FXExecutor
from services.fx_exchange.models import (
    InMemoryExecutionStore,
    InMemoryFXAudit,
    InMemoryOrderStore,
    InMemoryQuoteStore,
    InMemoryRateStore,
)
from services.fx_exchange.quote_engine import QuoteEngine
from services.fx_exchange.rate_provider import RateProvider
from services.fx_exchange.spread_manager import SpreadManager


def _make_agent() -> FXAgent:
    rate_store = InMemoryRateStore()
    quote_store = InMemoryQuoteStore()
    order_store = InMemoryOrderStore()
    execution_store = InMemoryExecutionStore()
    audit = InMemoryFXAudit()

    rate_provider = RateProvider(rate_store)
    quote_engine = QuoteEngine(rate_store, quote_store)
    fx_executor = FXExecutor(order_store, execution_store, audit)
    spread_manager = SpreadManager()
    fx_compliance = FXCompliance()

    return FXAgent(rate_provider, quote_engine, fx_executor, spread_manager, fx_compliance)


# ── get_live_rates ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_live_rates_all_supported():
    agent = _make_agent()
    rates = await agent.get_live_rates()
    assert len(rates) == 6


@pytest.mark.asyncio
async def test_get_live_rates_values_are_strings():
    agent = _make_agent()
    rates = await agent.get_live_rates()
    for pair_str, rate_str in rates.items():
        assert isinstance(rate_str, str)
        Decimal(rate_str)  # must be parseable as Decimal


@pytest.mark.asyncio
async def test_get_live_rates_specific_pairs():
    agent = _make_agent()
    rates = await agent.get_live_rates(["GBP/EUR", "GBP/USD"])
    assert "GBP/EUR" in rates
    assert "GBP/USD" in rates
    assert len(rates) == 2


@pytest.mark.asyncio
async def test_get_live_rates_gbp_eur_correct():
    agent = _make_agent()
    rates = await agent.get_live_rates(["GBP/EUR"])
    assert rates["GBP/EUR"] == "1.17"


# ── request_quote ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_request_quote_returns_dict():
    agent = _make_agent()
    result = await agent.request_quote("ent1", "GBP", "EUR", "1000")
    assert "quote_id" in result
    assert "rate" in result


@pytest.mark.asyncio
async def test_request_quote_amounts_are_strings():
    agent = _make_agent()
    result = await agent.request_quote("ent1", "GBP", "EUR", "1000")
    # All amounts must be strings (I-05)
    assert isinstance(result["rate"], str)
    assert isinstance(result["bid"], str)
    assert isinstance(result["ask"], str)
    assert isinstance(result["amount_base"], str)
    assert isinstance(result["amount_quote"], str)


@pytest.mark.asyncio
async def test_request_quote_sanctioned_currency_blocked():
    agent = _make_agent()
    result = await agent.request_quote("ent1", "GBP", "RUB", "100")
    assert result["status"] == "BLOCKED"


@pytest.mark.asyncio
async def test_request_quote_invalid_amount_raises():
    agent = _make_agent()
    with pytest.raises(ValueError, match="Invalid amount"):
        await agent.request_quote("ent1", "GBP", "EUR", "not-a-number")


@pytest.mark.asyncio
async def test_request_quote_compliance_flag_in_response():
    agent = _make_agent()
    result = await agent.request_quote("ent1", "GBP", "EUR", "5000")
    assert result["compliance_flag"] == "CLEAR"


@pytest.mark.asyncio
async def test_request_quote_edd_required_flag():
    agent = _make_agent()
    result = await agent.request_quote("ent1", "GBP", "EUR", "15000")
    assert result["compliance_flag"] == "EDD_REQUIRED"


# ── execute_fx (simple amount=1 path) ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_fx_returns_execution_dict():
    agent = _make_agent()
    quote_result = await agent.request_quote("ent1", "GBP", "EUR", "500")
    execution = await agent.execute_fx("ent1", quote_result["quote_id"])
    assert "execution_id" in execution
    assert "fee" in execution


@pytest.mark.asyncio
async def test_execute_fx_amounts_are_strings():
    agent = _make_agent()
    quote_result = await agent.request_quote("ent1", "GBP", "EUR", "500")
    execution = await agent.execute_fx("ent1", quote_result["quote_id"])
    assert isinstance(execution["fee"], str)
    assert isinstance(execution["rate"], str)


@pytest.mark.asyncio
async def test_execute_fx_invalid_quote_id_raises():
    agent = _make_agent()
    with pytest.raises(ValueError, match="not found"):
        await agent.execute_fx("ent1", "nonexistent-quote-id")


# ── execute_fx_with_amount (HITL path) ────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_fx_with_amount_hitl_required():
    agent = _make_agent()
    quote_result = await agent.request_quote("ent1", "GBP", "EUR", "1000")
    result = await agent.execute_fx_with_amount("ent1", quote_result["quote_id"], Decimal("60000"))
    assert result["status"] == "HITL_REQUIRED"


@pytest.mark.asyncio
async def test_execute_fx_with_amount_hitl_message():
    agent = _make_agent()
    quote_result = await agent.request_quote("ent1", "GBP", "EUR", "1000")
    result = await agent.execute_fx_with_amount("ent1", quote_result["quote_id"], Decimal("75000"))
    assert "50,000" in result["reason"]


@pytest.mark.asyncio
async def test_execute_fx_with_amount_normal_executes():
    agent = _make_agent()
    quote_result = await agent.request_quote("ent1", "GBP", "EUR", "1000")
    execution = await agent.execute_fx_with_amount(
        "ent1", quote_result["quote_id"], Decimal("1000")
    )
    assert "execution_id" in execution


# ── get_spread_info ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_spread_info_returns_dict():
    agent = _make_agent()
    result = await agent.get_spread_info("GBP", "EUR")
    assert result["pair"] == "GBP/EUR"
    assert "base_spread_bps" in result


@pytest.mark.asyncio
async def test_get_spread_info_major_pair():
    agent = _make_agent()
    result = await agent.get_spread_info("GBP", "EUR")
    assert result["base_spread_bps"] == 20


# ── get_fx_history ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_fx_history_empty_initially():
    agent = _make_agent()
    history = await agent.get_fx_history("ent-new")
    assert history == []


@pytest.mark.asyncio
async def test_get_fx_history_after_execution():
    agent = _make_agent()
    quote_result = await agent.request_quote("hist-ent", "GBP", "EUR", "500")
    await agent.execute_fx("hist-ent", quote_result["quote_id"])
    history = await agent.get_fx_history("hist-ent")
    assert len(history) == 1
    assert isinstance(history[0]["fee"], str)
