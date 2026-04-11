"""
tests/test_agent_routing/test_swarm_orchestrator.py — Swarm Orchestrator tests
IL-ARL-01 | banxe-emi-stack | 2026-04-11

Tests: star/hierarchy/ring topologies, aggregation rules, agent failures.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from services.agent_routing.models import AgentTask
from services.agent_routing.schemas import AgentResponse
from services.swarm.orchestrator import (
    SwarmOrchestrator,
    UnknownAgentError,
    UnknownTopologyError,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_task(risk_context: dict | None = None, jurisdiction: str = "EU") -> AgentTask:
    return AgentTask(
        task_id="swarm_test_001",
        event_type="aml_screening",
        tier=3,
        payload={"amount_eur": 5000},
        product="sepa_retail_transfer",
        jurisdiction=jurisdiction,
        customer_id="cust_swarm",
        risk_context=risk_context or {},
        created_at=datetime.now(UTC),
        playbook_id="eu_sepa_retail_v1",
    )


# ── Basic instantiation ────────────────────────────────────────────────────────


def test_orchestrator_instantiates() -> None:
    orch = SwarmOrchestrator()
    assert orch is not None


def test_orchestrator_lists_agents() -> None:
    orch = SwarmOrchestrator()
    agents = orch.list_agents()
    assert "sanctions" in agents
    assert "behavior" in agents
    assert "geo_risk" in agents
    assert "profile_history" in agents
    assert "product_limits" in agents


# ── Star topology ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_star_all_agents_run() -> None:
    orch = SwarmOrchestrator()
    task = make_task()
    result = await orch.launch_swarm(task, "star", ["sanctions", "behavior"])
    assert len(result.responses) == 2


@pytest.mark.asyncio
async def test_star_clean_returns_approve() -> None:
    orch = SwarmOrchestrator()
    task = make_task(
        risk_context={
            "sanctions_hit": False,
            "cumulative_risk_score": 0.05,
            "velocity_24h": 0,
            "amount_spike": False,
        }
    )
    result = await orch.launch_swarm(task, "star", ["sanctions", "behavior"])
    assert result.decision in ("approve", "manual_review")  # behavior may flag


@pytest.mark.asyncio
async def test_star_sanctions_hit_returns_hold() -> None:
    orch = SwarmOrchestrator()
    task = make_task(risk_context={"sanctions_hit": True})
    result = await orch.launch_swarm(task, "star", ["sanctions"])
    assert result.decision in ("hold", "decline")


@pytest.mark.asyncio
async def test_star_tier_used_is_3() -> None:
    orch = SwarmOrchestrator()
    task = make_task()
    result = await orch.launch_swarm(task, "star", ["sanctions"])
    assert result.tier_used == 3


@pytest.mark.asyncio
async def test_star_total_tokens_summed() -> None:
    orch = SwarmOrchestrator()
    task = make_task()
    result = await orch.launch_swarm(task, "star", ["sanctions", "behavior", "geo_risk"])
    total = sum(r.token_cost for r in result.responses)
    assert result.total_tokens == total


# ── Hierarchy topology ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hierarchy_coordinator_block_skips_subordinates() -> None:
    orch = SwarmOrchestrator()
    # sanctions agent will block RU jurisdiction
    task = make_task(jurisdiction="RU")
    result = await orch.launch_swarm(task, "hierarchy", ["sanctions", "behavior", "geo_risk"])
    # With block confidence=1.0 >= 0.85, subordinates skipped
    assert result.responses[0].agent_name == "sanctions_agent"
    assert len(result.responses) == 1
    assert result.decision in ("hold", "decline")


@pytest.mark.asyncio
async def test_hierarchy_clean_coordinator_runs_subordinates() -> None:
    orch = SwarmOrchestrator()
    task = make_task(risk_context={"sanctions_hit": False})
    result = await orch.launch_swarm(task, "hierarchy", ["sanctions", "behavior"])
    # Both should run (no block)
    assert len(result.responses) >= 2


@pytest.mark.asyncio
async def test_hierarchy_single_agent() -> None:
    orch = SwarmOrchestrator()
    task = make_task()
    result = await orch.launch_swarm(task, "hierarchy", ["sanctions"])
    assert len(result.responses) == 1


# ── Ring topology ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ring_sequential_all_agents() -> None:
    orch = SwarmOrchestrator()
    task = make_task(risk_context={"sanctions_hit": False})
    result = await orch.launch_swarm(task, "ring", ["geo_risk", "profile_history"])
    assert len(result.responses) == 2


@pytest.mark.asyncio
async def test_ring_short_circuits_on_block() -> None:
    orch = SwarmOrchestrator()
    task = make_task(jurisdiction="IR")  # sanctioned → block
    result = await orch.launch_swarm(task, "ring", ["sanctions", "behavior", "geo_risk"])
    # Ring short-circuits after sanctions block
    assert result.responses[0].agent_name == "sanctions_agent"
    assert len(result.responses) == 1


@pytest.mark.asyncio
async def test_ring_returns_valid_decision() -> None:
    orch = SwarmOrchestrator()
    task = make_task()
    result = await orch.launch_swarm(task, "ring", ["geo_risk"])
    assert result.decision in ("approve", "decline", "manual_review", "hold")


# ── Aggregation rules ──────────────────────────────────────────────────────────


def test_aggregate_block_high_confidence_returns_hold() -> None:
    orch = SwarmOrchestrator()
    responses = [
        AgentResponse(
            agent_name="sanctions_agent",
            case_id="t1",
            signal_type="sanctions",
            risk_score=1.0,
            confidence=0.95,
            decision_hint="block",
            reason_summary="Sanctions hit",
            evidence_refs=[],
            token_cost=0,
            latency_ms=0,
        )
    ]
    assert orch._aggregate(responses) == "hold"


def test_aggregate_block_low_confidence_returns_decline() -> None:
    orch = SwarmOrchestrator()
    responses = [
        AgentResponse(
            agent_name="test_agent",
            case_id="t1",
            signal_type="test",
            risk_score=0.9,
            confidence=0.5,  # below 0.85 threshold
            decision_hint="block",
            reason_summary="Block",
            evidence_refs=[],
            token_cost=0,
            latency_ms=0,
        )
    ]
    assert orch._aggregate(responses) == "decline"


def test_aggregate_three_warnings_returns_manual_review() -> None:
    orch = SwarmOrchestrator()
    responses = [
        AgentResponse(
            agent_name=f"agent_{i}",
            case_id="t1",
            signal_type="test",
            risk_score=0.5,
            confidence=0.8,
            decision_hint="warning",
            reason_summary="Warning",
            evidence_refs=[],
            token_cost=0,
            latency_ms=0,
        )
        for i in range(3)
    ]
    assert orch._aggregate(responses) == "manual_review"


def test_aggregate_all_clear_low_risk_approves() -> None:
    orch = SwarmOrchestrator()
    responses = [
        AgentResponse(
            agent_name=f"agent_{i}",
            case_id="t1",
            signal_type="test",
            risk_score=0.1,
            confidence=0.95,
            decision_hint="clear",
            reason_summary="Clear",
            evidence_refs=[],
            token_cost=0,
            latency_ms=0,
        )
        for i in range(3)
    ]
    assert orch._aggregate(responses) == "approve"


def test_aggregate_empty_returns_manual_review() -> None:
    orch = SwarmOrchestrator()
    assert orch._aggregate([]) == "manual_review"


# ── Error handling ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_topology_raises() -> None:
    orch = SwarmOrchestrator()
    task = make_task()
    with pytest.raises(UnknownTopologyError):
        await orch.launch_swarm(task, "unknown_topology", ["sanctions"])


@pytest.mark.asyncio
async def test_unknown_agent_raises() -> None:
    orch = SwarmOrchestrator()
    task = make_task()
    with pytest.raises(UnknownAgentError):
        await orch.launch_swarm(task, "star", ["nonexistent_agent"])


@pytest.mark.asyncio
async def test_playbook_version_set_in_result() -> None:
    orch = SwarmOrchestrator()
    task = make_task()
    result = await orch.launch_swarm(task, "star", ["sanctions"])
    assert result.playbook_version == "eu_sepa_retail_v1"
