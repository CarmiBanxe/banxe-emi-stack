"""
tests/test_agent_routing/test_telemetry.py — ARL Telemetry tests
IL-ARL-01 | banxe-emi-stack | 2026-04-11

Tests: metrics emission, cost calculation, ClickHouse writes.
"""

from __future__ import annotations

import pytest

from services.agent_routing.telemetry import ARLTelemetry, InMemoryClickHouse

# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def ch() -> InMemoryClickHouse:
    return InMemoryClickHouse()


@pytest.fixture
def telemetry(ch: InMemoryClickHouse) -> ARLTelemetry:
    return ARLTelemetry(clickhouse=ch)


# ── InMemoryClickHouse ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_in_memory_ch_inserts_rows(ch: InMemoryClickHouse) -> None:
    await ch.insert("test_table", [{"col": "val"}])
    assert len(ch.rows) == 1
    assert ch.rows[0]["table"] == "test_table"
    assert ch.rows[0]["col"] == "val"


@pytest.mark.asyncio
async def test_in_memory_ch_multiple_rows(ch: InMemoryClickHouse) -> None:
    await ch.insert("t", [{"a": 1}, {"a": 2}, {"a": 3}])
    assert len(ch.rows) == 3


# ── ARLTelemetry: emit_routing_event ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_emit_routing_event_stored(telemetry: ARLTelemetry, ch: InMemoryClickHouse) -> None:
    await telemetry.emit_routing_event(
        task_id="task_001",
        tier=1,
        event_type="aml_screening",
        product="sepa_retail_transfer",
        jurisdiction="EU",
        total_tokens=0,
        latency_ms=5,
        decision="approve",
        reasoning_reused=False,
    )
    assert len(ch.rows) == 1
    row = ch.rows[0]
    assert row["task_id"] == "task_001"
    assert row["tier"] == 1
    assert row["decision"] == "approve"


@pytest.mark.asyncio
async def test_emit_routing_event_reasoning_reused_flag(
    telemetry: ARLTelemetry, ch: InMemoryClickHouse
) -> None:
    await telemetry.emit_routing_event(
        task_id="task_002",
        tier=2,
        event_type="kyc_check",
        product="fps_retail_transfer",
        jurisdiction="UK",
        total_tokens=300,
        latency_ms=150,
        decision="manual_review",
        reasoning_reused=True,
    )
    row = ch.rows[0]
    assert row["reasoning_reused"] == 1


@pytest.mark.asyncio
async def test_emit_routing_event_cost_computed(
    telemetry: ARLTelemetry, ch: InMemoryClickHouse
) -> None:
    await telemetry.emit_routing_event(
        task_id="task_003",
        tier=2,
        event_type="test",
        product="test",
        jurisdiction="EU",
        total_tokens=1000,
        latency_ms=100,
        decision="approve",
        reasoning_reused=False,
    )
    row = ch.rows[0]
    # Tier 2: $0.025 per 1k tokens — 1000 tokens = $0.025
    assert row["cost_usd"] == pytest.approx(0.025, rel=0.01)


@pytest.mark.asyncio
async def test_emit_tier1_zero_cost(telemetry: ARLTelemetry, ch: InMemoryClickHouse) -> None:
    await telemetry.emit_routing_event(
        task_id="task_004",
        tier=1,
        event_type="test",
        product="test",
        jurisdiction="EU",
        total_tokens=0,
        latency_ms=2,
        decision="approve",
        reasoning_reused=False,
    )
    row = ch.rows[0]
    assert row["cost_usd"] == 0.0


@pytest.mark.asyncio
async def test_emit_tier3_higher_cost(telemetry: ARLTelemetry, ch: InMemoryClickHouse) -> None:
    await telemetry.emit_routing_event(
        task_id="task_005",
        tier=3,
        event_type="test",
        product="test",
        jurisdiction="EU",
        total_tokens=1000,
        latency_ms=500,
        decision="manual_review",
        reasoning_reused=False,
    )
    row = ch.rows[0]
    # Tier 3: $0.150 per 1k
    assert row["cost_usd"] == pytest.approx(0.150, rel=0.01)


@pytest.mark.asyncio
async def test_emit_agent_response(telemetry: ARLTelemetry, ch: InMemoryClickHouse) -> None:
    await telemetry.emit_agent_response(
        task_id="task_006",
        agent_name="sanctions_agent",
        signal_type="sanctions_screening",
        risk_score=0.0,
        confidence=0.98,
        decision_hint="clear",
        token_cost=0,
        latency_ms=3,
    )
    assert any(r.get("agent_name") == "sanctions_agent" for r in ch.rows)


@pytest.mark.asyncio
async def test_telemetry_exception_not_propagated(
    telemetry: ARLTelemetry,
) -> None:
    """Telemetry failures must not crash the routing pipeline."""

    class FailingCH:
        async def insert(self, table: str, rows: list) -> None:
            raise RuntimeError("ClickHouse unavailable")

    bad_telemetry = ARLTelemetry(clickhouse=FailingCH())
    # Should not raise
    await bad_telemetry.emit_routing_event(
        task_id="task_007",
        tier=1,
        event_type="test",
        product="test",
        jurisdiction="EU",
        total_tokens=0,
        latency_ms=0,
        decision="approve",
        reasoning_reused=False,
    )


# ── Cost computation ───────────────────────────────────────────────────────────


def test_compute_cost_tier1_zero(telemetry: ARLTelemetry) -> None:
    assert telemetry.compute_cost_usd(1, 10000) == 0.0


def test_compute_cost_tier2(telemetry: ARLTelemetry) -> None:
    cost = telemetry.compute_cost_usd(2, 1000)
    assert cost == pytest.approx(0.025, rel=0.01)


def test_compute_cost_tier3(telemetry: ARLTelemetry) -> None:
    cost = telemetry.compute_cost_usd(3, 1000)
    assert cost == pytest.approx(0.150, rel=0.01)


def test_compute_cost_unknown_tier_uses_high(telemetry: ARLTelemetry) -> None:
    cost = telemetry.compute_cost_usd(99, 1000)
    assert cost == pytest.approx(0.150, rel=0.01)
