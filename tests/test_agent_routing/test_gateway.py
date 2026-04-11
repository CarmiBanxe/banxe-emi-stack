"""
tests/test_agent_routing/test_gateway.py — Agent Gateway tests
IL-ARL-01 | banxe-emi-stack | 2026-04-11

Tests: event normalization, routing decisions, ReasoningBank integration.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from services.agent_routing.gateway import AgentGateway, NullReasoningBank, NullTelemetry
from services.agent_routing.playbook_engine import PlaybookEngine
from services.agent_routing.schemas import TierResult

# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def gateway() -> AgentGateway:
    return AgentGateway()


@pytest.fixture
def low_risk_ctx() -> dict:
    return {
        "known_beneficiary": True,
        "sanctions_hit": False,
        "device_risk": "low",
        "anomaly_count": 0,
        "amount_eur": 500,
        "customer_type": "individual",
    }


@pytest.fixture
def sanctions_ctx() -> dict:
    return {
        "sanctions_hit": True,
        "cumulative_risk_score": 0.90,
        "amount_eur": 5000,
    }


# ── Gateway construction ───────────────────────────────────────────────────────


def test_gateway_instantiates() -> None:
    gw = AgentGateway()
    assert gw is not None


def test_gateway_with_custom_engine() -> None:
    engine = PlaybookEngine()
    gw = AgentGateway(playbook_engine=engine)
    assert gw is not None


def test_gateway_with_null_components() -> None:
    gw = AgentGateway(
        reasoning_bank=NullReasoningBank(),
        telemetry=NullTelemetry(),
    )
    assert gw is not None


# ── NullReasoningBank ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_null_reasoning_bank_find_similar() -> None:
    rb = NullReasoningBank()
    result = await rb.find_similar("aml_screening", {}, top_k=5)
    assert result == []


@pytest.mark.asyncio
async def test_null_reasoning_bank_get_reasoning() -> None:
    rb = NullReasoningBank()
    result = await rb.get_reusable_reasoning("case_123")
    assert result is None


# ── NullTelemetry ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_null_telemetry_emit() -> None:
    telem = NullTelemetry()
    # Should not raise
    await telem.emit_routing_event(
        task_id="t1",
        tier=1,
        event_type="test",
        product="sepa_retail_transfer",
        jurisdiction="EU",
        total_tokens=0,
        latency_ms=0,
        decision="approve",
        reasoning_reused=False,
    )


# ── Event normalization ────────────────────────────────────────────────────────


def test_normalize_event_extracts_fields(gateway: AgentGateway) -> None:
    domain_event = {
        "event_type": "aml_screening",
        "product": "sepa_retail_transfer",
        "jurisdiction": "EU",
        "customer_id": "cust_001",
        "payload": {"amount_eur": 500},
        "risk_context": {"known_beneficiary": True},
    }
    normalized = gateway.normalize_event(domain_event)
    assert normalized["event_type"] == "aml_screening"
    assert normalized["product"] == "sepa_retail_transfer"
    assert normalized["customer_id"] == "cust_001"


def test_normalize_event_handles_missing_fields(gateway: AgentGateway) -> None:
    normalized = gateway.normalize_event({})
    assert normalized["event_type"] == "unknown"
    assert normalized["product"] == "unknown"
    assert normalized["jurisdiction"] == "unknown"
    assert normalized["customer_id"] == ""
    assert normalized["payload"] == {}
    assert normalized["risk_context"] == {}


# ── Process — routing decisions ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_low_risk_eu_sepa(gateway: AgentGateway, low_risk_ctx: dict) -> None:
    result = await gateway.process(
        event_type="aml_screening",
        product="sepa_retail_transfer",
        jurisdiction="EU",
        customer_id="cust_001",
        payload={"amount_eur": 500},
        risk_context=low_risk_ctx,
    )
    assert isinstance(result, TierResult)
    assert result.tier_used in (1, 2, 3)
    assert result.decision in ("approve", "decline", "manual_review", "hold")


@pytest.mark.asyncio
async def test_process_sanctions_hit_returns_hold_or_decline(
    gateway: AgentGateway, sanctions_ctx: dict
) -> None:
    result = await gateway.process(
        event_type="aml_screening",
        product="sepa_retail_transfer",
        jurisdiction="EU",
        customer_id="cust_002",
        payload={"amount_eur": 5000},
        risk_context=sanctions_ctx,
    )
    assert result.decision in ("hold", "decline", "manual_review")


@pytest.mark.asyncio
async def test_process_returns_tier_result(gateway: AgentGateway) -> None:
    result = await gateway.process(
        event_type="kyc_check",
        product="sepa_retail_transfer",
        jurisdiction="EU",
        customer_id="cust_003",
        payload={},
        risk_context={},
    )
    assert result.task_id is not None
    assert result.playbook_version == "eu_sepa_retail_v1"


@pytest.mark.asyncio
async def test_process_unknown_product_defaults_tier3(gateway: AgentGateway) -> None:
    result = await gateway.process(
        event_type="unknown_event",
        product="unknown_product_xyz",
        jurisdiction="ZZ",
        customer_id="cust_004",
        payload={},
        risk_context={"cumulative_risk_score": 0.5},
    )
    # Should still return a valid result (default_fallback tier 3)
    assert result.tier_used == 3
    assert result.playbook_version == "default_fallback"


@pytest.mark.asyncio
async def test_process_sets_task_id(gateway: AgentGateway) -> None:
    result = await gateway.process(
        event_type="aml_screening",
        product="sepa_retail_transfer",
        jurisdiction="EU",
        customer_id="cust_005",
        payload={},
        risk_context={
            "known_beneficiary": True,
            "sanctions_hit": False,
            "device_risk": "low",
            "anomaly_count": 0,
            "amount_eur": 100,
        },
    )
    assert len(result.task_id) > 0


@pytest.mark.asyncio
async def test_process_explicit_task_id(gateway: AgentGateway) -> None:
    result = await gateway.process(
        event_type="aml_screening",
        product="sepa_retail_transfer",
        jurisdiction="EU",
        customer_id="cust_006",
        payload={},
        risk_context={},
        task_id="explicit_task_001",
    )
    assert result.task_id == "explicit_task_001"


@pytest.mark.asyncio
async def test_process_reasoning_bank_cache_miss(gateway: AgentGateway) -> None:
    result = await gateway.process(
        event_type="aml_screening",
        product="sepa_retail_transfer",
        jurisdiction="EU",
        customer_id="cust_007",
        payload={},
        risk_context={},
    )
    assert result.reasoning_reused is False


@pytest.mark.asyncio
async def test_process_reasoning_bank_cache_hit() -> None:
    """Gateway marks reasoning_reused when ReasoningBank returns a hint."""
    mock_rb = AsyncMock()
    mock_rb.find_similar.return_value = [{"case_id": "prev_case_001"}]
    mock_rb.get_reusable_reasoning.return_value = {
        "internal_view": "prior reasoning",
        "audit_view": "audit trail",
        "customer_view": "plain explanation",
    }
    gw = AgentGateway(reasoning_bank=mock_rb)
    result = await gw.process(
        event_type="aml_screening",
        product="sepa_retail_transfer",
        jurisdiction="EU",
        customer_id="cust_008",
        payload={},
        risk_context={},
    )
    assert result.reasoning_reused is True


@pytest.mark.asyncio
async def test_process_total_latency_set(gateway: AgentGateway) -> None:
    result = await gateway.process(
        event_type="aml_screening",
        product="sepa_retail_transfer",
        jurisdiction="EU",
        customer_id="cust_009",
        payload={},
        risk_context={},
    )
    assert result.total_latency_ms >= 0
