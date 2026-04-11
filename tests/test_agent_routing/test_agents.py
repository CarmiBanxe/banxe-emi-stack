"""
tests/test_agent_routing/test_agents.py — Specialized agent tests
IL-ARL-01 | banxe-emi-stack | 2026-04-11

Tests: each specialized agent returns valid AgentResponse.
Covers sanctions, behavior, geo_risk, profile_history, product_limits.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from services.agent_routing.models import AgentTask
from services.agent_routing.schemas import AgentResponse
from services.swarm.agents.behavior_agent import BehaviorAgent
from services.swarm.agents.geo_risk_agent import GeoRiskAgent
from services.swarm.agents.product_limits_agent import ProductLimitsAgent
from services.swarm.agents.profile_history_agent import ProfileHistoryAgent
from services.swarm.agents.sanctions_agent import SanctionsAgent

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_task(
    jurisdiction: str = "EU",
    risk_context: dict | None = None,
    payload: dict | None = None,
    product: str = "sepa_retail_transfer",
) -> AgentTask:
    return AgentTask(
        task_id="agent_test_001",
        event_type="aml_screening",
        tier=3,
        payload=payload or {},
        product=product,
        jurisdiction=jurisdiction,
        customer_id="cust_agent_test",
        risk_context=risk_context or {},
        created_at=datetime.now(UTC),
        playbook_id="eu_sepa_retail_v1",
    )


def assert_valid_response(resp: AgentResponse) -> None:
    """Common response validation."""
    assert isinstance(resp, AgentResponse)
    assert 0.0 <= resp.risk_score <= 1.0
    assert 0.0 <= resp.confidence <= 1.0
    assert resp.decision_hint in ("clear", "warning", "block", "manual_review")
    assert isinstance(resp.reason_summary, str)
    assert isinstance(resp.evidence_refs, list)
    assert resp.token_cost >= 0
    assert resp.latency_ms >= 0


# ── SanctionsAgent ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sanctions_agent_name() -> None:
    agent = SanctionsAgent()
    assert agent.agent_name == "sanctions_agent"


@pytest.mark.asyncio
async def test_sanctions_signal_type() -> None:
    agent = SanctionsAgent()
    assert agent.signal_type == "sanctions_screening"


@pytest.mark.asyncio
async def test_sanctions_agent_clean() -> None:
    agent = SanctionsAgent()
    resp = await agent.analyze(make_task())
    assert_valid_response(resp)
    assert resp.decision_hint == "clear"
    assert resp.risk_score < 0.1


@pytest.mark.asyncio
async def test_sanctions_agent_sanctions_hit() -> None:
    agent = SanctionsAgent()
    resp = await agent.analyze(make_task(risk_context={"sanctions_hit": True}))
    assert resp.decision_hint == "block"
    assert resp.risk_score == 1.0
    assert resp.confidence == 1.0


@pytest.mark.asyncio
async def test_sanctions_agent_pep_match() -> None:
    agent = SanctionsAgent()
    resp = await agent.analyze(make_task(risk_context={"pep_match": True}))
    assert resp.decision_hint == "warning"
    assert resp.risk_score == 0.7


@pytest.mark.asyncio
async def test_sanctions_blocked_jurisdiction_ru() -> None:
    agent = SanctionsAgent()
    resp = await agent.analyze(make_task(jurisdiction="RU"))
    assert resp.decision_hint == "block"
    assert "RU" in resp.reason_summary


@pytest.mark.asyncio
async def test_sanctions_blocked_iban_prefix() -> None:
    agent = SanctionsAgent()
    resp = await agent.analyze(make_task(payload={"beneficiary_iban": "IR123456789"}))
    assert resp.decision_hint == "block"


@pytest.mark.asyncio
async def test_sanctions_token_cost_zero() -> None:
    agent = SanctionsAgent()
    resp = await agent.analyze(make_task())
    assert resp.token_cost == 0  # rule-based, no LLM


# ── BehaviorAgent ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_behavior_agent_name() -> None:
    assert BehaviorAgent().agent_name == "behavior_agent"


@pytest.mark.asyncio
async def test_behavior_signal_type() -> None:
    assert BehaviorAgent().signal_type == "behavioral_anomaly"


@pytest.mark.asyncio
async def test_behavior_clean() -> None:
    agent = BehaviorAgent()
    resp = await agent.analyze(make_task())
    assert_valid_response(resp)
    assert resp.decision_hint == "clear"


@pytest.mark.asyncio
async def test_behavior_high_velocity() -> None:
    agent = BehaviorAgent()
    resp = await agent.analyze(make_task(risk_context={"velocity_24h": 15}))
    assert resp.risk_score > 0.2


@pytest.mark.asyncio
async def test_behavior_structuring_detected() -> None:
    agent = BehaviorAgent()
    resp = await agent.analyze(make_task(risk_context={"structuring_detected": True}))
    assert resp.risk_score >= 0.4


@pytest.mark.asyncio
async def test_behavior_off_hours_transaction() -> None:
    agent = BehaviorAgent()
    resp = await agent.analyze(make_task(risk_context={"hour_utc": 3}))
    assert resp.risk_score > 0.0


@pytest.mark.asyncio
async def test_behavior_amount_spike() -> None:
    agent = BehaviorAgent()
    resp = await agent.analyze(make_task(risk_context={"amount_spike": True}))
    assert resp.risk_score >= 0.3


# ── GeoRiskAgent ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_geo_risk_agent_name() -> None:
    assert GeoRiskAgent().agent_name == "geo_risk_agent"


@pytest.mark.asyncio
async def test_geo_risk_signal_type() -> None:
    assert GeoRiskAgent().signal_type == "geo_risk"


@pytest.mark.asyncio
async def test_geo_risk_eu_clean() -> None:
    agent = GeoRiskAgent()
    resp = await agent.analyze(make_task(jurisdiction="EU"))
    assert resp.decision_hint == "clear"
    assert resp.risk_score < 0.3


@pytest.mark.asyncio
async def test_geo_risk_sanctioned_jurisdiction() -> None:
    agent = GeoRiskAgent()
    for juris in ("RU", "IR", "KP"):
        resp = await agent.analyze(make_task(jurisdiction=juris))
        assert resp.decision_hint == "block"
        assert resp.risk_score == 1.0, f"Expected risk=1.0 for {juris}"


@pytest.mark.asyncio
async def test_geo_risk_fatf_greylist() -> None:
    agent = GeoRiskAgent()
    resp = await agent.analyze(make_task(jurisdiction="NG"))  # Nigeria — FATF greylist
    assert resp.decision_hint == "warning"
    assert resp.risk_score >= 0.5


@pytest.mark.asyncio
async def test_geo_risk_beneficiary_country_checked() -> None:
    agent = GeoRiskAgent()
    resp = await agent.analyze(
        make_task(
            jurisdiction="EU",
            payload={"beneficiary_country": "NG"},
        )
    )
    # Beneficiary in NG (FATF greylist) should elevate risk
    assert resp.risk_score > 0.1


# ── ProfileHistoryAgent ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_profile_history_agent_name() -> None:
    assert ProfileHistoryAgent().agent_name == "profile_history_agent"


@pytest.mark.asyncio
async def test_profile_history_signal_type() -> None:
    assert ProfileHistoryAgent().signal_type == "profile_history"


@pytest.mark.asyncio
async def test_profile_history_clean() -> None:
    agent = ProfileHistoryAgent()
    resp = await agent.analyze(
        make_task(risk_context={"customer_age_days": 365, "kyc_level": "enhanced"})
    )
    assert_valid_response(resp)
    assert resp.risk_score < 0.3


@pytest.mark.asyncio
async def test_profile_history_previous_sar() -> None:
    agent = ProfileHistoryAgent()
    resp = await agent.analyze(make_task(risk_context={"previous_sar": True}))
    assert resp.risk_score >= 0.5


@pytest.mark.asyncio
async def test_profile_history_compliance_flags() -> None:
    agent = ProfileHistoryAgent()
    resp = await agent.analyze(make_task(risk_context={"compliance_flags": 3}))
    assert resp.risk_score >= 0.35


@pytest.mark.asyncio
async def test_profile_history_new_customer() -> None:
    agent = ProfileHistoryAgent()
    resp = await agent.analyze(make_task(risk_context={"customer_age_days": 5}))
    assert resp.risk_score > 0.1


# ── ProductLimitsAgent ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_product_limits_agent_name() -> None:
    assert ProductLimitsAgent().agent_name == "product_limits_agent"


@pytest.mark.asyncio
async def test_product_limits_signal_type() -> None:
    assert ProductLimitsAgent().signal_type == "product_limits"


@pytest.mark.asyncio
async def test_product_limits_within_limit() -> None:
    agent = ProductLimitsAgent()
    resp = await agent.analyze(make_task(payload={"amount_eur": "500"}))
    assert resp.decision_hint == "clear"
    assert resp.risk_score == 0.0


@pytest.mark.asyncio
async def test_product_limits_exceeds_single_max() -> None:
    agent = ProductLimitsAgent()
    resp = await agent.analyze(make_task(payload={"amount_eur": "60000"}))
    assert resp.decision_hint == "block"
    assert resp.risk_score >= 0.7


@pytest.mark.asyncio
async def test_product_limits_edd_threshold_individual() -> None:
    agent = ProductLimitsAgent()
    resp = await agent.analyze(
        make_task(
            payload={"amount_eur": "12000"},
            risk_context={"customer_type": "individual"},
        )
    )
    assert resp.decision_hint == "warning"


@pytest.mark.asyncio
async def test_product_limits_corporate_edd_higher() -> None:
    agent = ProductLimitsAgent()
    resp = await agent.analyze(
        make_task(
            payload={"amount_eur": "30000"},
            risk_context={"customer_type": "corporate"},
        )
    )
    # 30k < 50k corporate EDD — should be clear
    assert resp.decision_hint == "clear"


@pytest.mark.asyncio
async def test_product_limits_unknown_product_uses_default() -> None:
    agent = ProductLimitsAgent()
    resp = await agent.analyze(
        make_task(
            product="unknown_product",
            payload={"amount_eur": "500"},
        )
    )
    assert_valid_response(resp)


@pytest.mark.asyncio
async def test_product_limits_confidence_is_one() -> None:
    """Product limits check is deterministic — confidence must be 1.0."""
    agent = ProductLimitsAgent()
    resp = await agent.analyze(make_task(payload={"amount_eur": "500"}))
    assert resp.confidence == 1.0
