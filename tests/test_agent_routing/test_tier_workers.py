"""
tests/test_agent_routing/test_tier_workers.py — Tier Worker tests
IL-ARL-01 | banxe-emi-stack | 2026-04-11

Tests: Tier1/2/3 workers process tasks correctly,
aggregation logic, sanctioned jurisdiction blocks.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from services.agent_routing.models import AgentTask
from services.agent_routing.tier_workers import Tier1Worker, Tier2Worker, Tier3Worker

# ── Fixtures ───────────────────────────────────────────────────────────────────


def make_task(
    tier: int = 1,
    risk_context: dict | None = None,
    payload: dict | None = None,
    jurisdiction: str = "EU",
    product: str = "sepa_retail_transfer",
) -> AgentTask:
    return AgentTask(
        task_id="test_task_001",
        event_type="aml_screening",
        tier=tier,
        payload=payload or {},
        product=product,
        jurisdiction=jurisdiction,
        customer_id="cust_test",
        risk_context=risk_context or {},
        created_at=datetime.now(UTC),
        playbook_id="eu_sepa_retail_v1",
    )


# ── AgentTask validation ───────────────────────────────────────────────────────


def test_agent_task_invalid_tier_raises() -> None:
    with pytest.raises(ValueError, match="tier must be 1, 2 or 3"):
        make_task(tier=0)


def test_agent_task_invalid_tier_4_raises() -> None:
    with pytest.raises(ValueError):
        make_task(tier=4)


def test_agent_task_empty_task_id_raises() -> None:
    with pytest.raises(ValueError, match="task_id must not be empty"):
        AgentTask(
            task_id="",
            event_type="test",
            tier=1,
            payload={},
            product="test",
            jurisdiction="EU",
            customer_id="cust",
            risk_context={},
            created_at=datetime.now(UTC),
            playbook_id="test",
        )


# ── Tier 1: Sanctions checks ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tier1_sanctions_clean() -> None:
    worker = Tier1Worker()
    task = make_task(tier=1, risk_context={"sanctions_hit": False}, jurisdiction="EU")
    result = await worker.process(task)
    sanctions_resp = next(r for r in result.responses if r.agent_name == "tier1_sanctions")
    assert sanctions_resp.decision_hint == "clear"
    assert sanctions_resp.risk_score == 0.0


@pytest.mark.asyncio
async def test_tier1_sanctions_hit_blocks() -> None:
    worker = Tier1Worker()
    task = make_task(tier=1, risk_context={"sanctions_hit": True})
    result = await worker.process(task)
    sanctions_resp = next(r for r in result.responses if r.agent_name == "tier1_sanctions")
    assert sanctions_resp.decision_hint == "block"
    assert sanctions_resp.risk_score == 1.0


@pytest.mark.asyncio
async def test_tier1_sanctioned_jurisdiction_blocks() -> None:
    worker = Tier1Worker()
    task = make_task(tier=1, jurisdiction="RU")
    result = await worker.process(task)
    assert result.decision in ("hold", "decline")


@pytest.mark.asyncio
async def test_tier1_all_sanctioned_jurisdictions() -> None:
    worker = Tier1Worker()
    for juris in ("RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"):
        task = make_task(tier=1, jurisdiction=juris)
        result = await worker.process(task)
        assert result.decision in ("hold", "decline"), f"Expected block for {juris}"


# ── Tier 1: Limit checks ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tier1_edd_individual_threshold() -> None:
    worker = Tier1Worker()
    task = make_task(
        tier=1,
        risk_context={"amount_eur": 15000, "customer_type": "individual"},
    )
    result = await worker.process(task)
    limit_resp = next(r for r in result.responses if r.agent_name == "tier1_limits")
    assert limit_resp.decision_hint == "warning"


@pytest.mark.asyncio
async def test_tier1_edd_corporate_threshold_higher() -> None:
    worker = Tier1Worker()
    # 30k is below corporate EDD threshold of 50k
    task = make_task(
        tier=1,
        risk_context={"amount_eur": 30000, "customer_type": "corporate"},
    )
    result = await worker.process(task)
    limit_resp = next(r for r in result.responses if r.agent_name == "tier1_limits")
    assert limit_resp.decision_hint == "clear"


@pytest.mark.asyncio
async def test_tier1_amount_within_limits() -> None:
    worker = Tier1Worker()
    task = make_task(tier=1, risk_context={"amount_eur": 500})
    result = await worker.process(task)
    limit_resp = next(r for r in result.responses if r.agent_name == "tier1_limits")
    assert limit_resp.decision_hint == "clear"


# ── Tier 1: Pattern matching ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tier1_known_safe_pattern() -> None:
    worker = Tier1Worker()
    task = make_task(
        tier=1,
        risk_context={"known_beneficiary": True, "anomaly_count": 0, "device_risk": "low"},
    )
    result = await worker.process(task)
    pattern_resp = next(r for r in result.responses if r.agent_name == "tier1_pattern")
    assert pattern_resp.decision_hint == "clear"
    assert pattern_resp.risk_score < 0.1


@pytest.mark.asyncio
async def test_tier1_anomaly_increases_risk() -> None:
    worker = Tier1Worker()
    task = make_task(tier=1, risk_context={"anomaly_count": 3, "device_risk": "high"})
    result = await worker.process(task)
    pattern_resp = next(r for r in result.responses if r.agent_name == "tier1_pattern")
    assert pattern_resp.risk_score > 0.3


# ── Tier 1: Aggregation ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tier1_clean_path_approves() -> None:
    worker = Tier1Worker()
    task = make_task(
        tier=1,
        risk_context={
            "known_beneficiary": True,
            "sanctions_hit": False,
            "device_risk": "low",
            "anomaly_count": 0,
            "amount_eur": 100,
        },
    )
    result = await worker.process(task)
    assert result.decision == "approve"
    assert result.tier_used == 1
    assert result.total_tokens == 0


@pytest.mark.asyncio
async def test_tier1_result_has_responses() -> None:
    worker = Tier1Worker()
    task = make_task(tier=1)
    result = await worker.process(task)
    assert len(result.responses) == 3  # sanctions, limits, pattern


# ── Tier 2 ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tier2_new_beneficiary_routes_warning() -> None:
    worker = Tier2Worker()
    task = make_task(tier=2, risk_context={"new_beneficiary": True, "customer_age_days": 10})
    result = await worker.process(task)
    ben_resp = next(r for r in result.responses if r.agent_name == "tier2_beneficiary")
    assert ben_resp.decision_hint == "warning"


@pytest.mark.asyncio
async def test_tier2_suspicious_description() -> None:
    worker = Tier2Worker()
    task = make_task(
        tier=2,
        payload={"description": "crypto gambling offshore"},
        risk_context={},
    )
    result = await worker.process(task)
    desc_resp = next(r for r in result.responses if r.agent_name == "tier2_description_nlp")
    assert desc_resp.decision_hint == "warning"


@pytest.mark.asyncio
async def test_tier2_clean_description() -> None:
    worker = Tier2Worker()
    task = make_task(tier=2, payload={"description": "rent payment"}, risk_context={})
    result = await worker.process(task)
    desc_resp = next(r for r in result.responses if r.agent_name == "tier2_description_nlp")
    assert desc_resp.decision_hint == "clear"


@pytest.mark.asyncio
async def test_tier2_high_velocity_flags_behavior() -> None:
    worker = Tier2Worker()
    task = make_task(tier=2, risk_context={"velocity_24h": 20, "cumulative_risk_score": 0.5})
    result = await worker.process(task)
    behavior_resp = next(r for r in result.responses if r.agent_name == "tier2_behavior")
    assert behavior_resp.risk_score > 0.5


@pytest.mark.asyncio
async def test_tier2_result_structure() -> None:
    worker = Tier2Worker()
    task = make_task(tier=2)
    result = await worker.process(task)
    assert result.tier_used == 2
    assert len(result.responses) == 3
    assert result.total_tokens > 0


# ── Tier 3 ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tier3_sanctions_hit_declines() -> None:
    worker = Tier3Worker()
    task = make_task(tier=3, risk_context={"sanctions_hit": True, "cumulative_risk_score": 0.9})
    result = await worker.process(task)
    assert result.decision == "decline"
    assert result.tier_used == 3


@pytest.mark.asyncio
async def test_tier3_high_cumulative_risk_manual_review() -> None:
    worker = Tier3Worker()
    task = make_task(tier=3, risk_context={"cumulative_risk_score": 0.80})
    result = await worker.process(task)
    assert result.decision == "manual_review"


@pytest.mark.asyncio
async def test_tier3_conflicting_signals_uses_swarm() -> None:
    worker = Tier3Worker()
    task = make_task(
        tier=3,
        risk_context={
            "conflicting_signals": True,
            "cross_border": True,
            "cumulative_risk_score": 0.5,
        },
    )
    # Should use swarm path; result must be valid
    result = await worker.process(task)
    assert result.tier_used == 3
    assert result.decision in ("approve", "decline", "manual_review", "hold")
