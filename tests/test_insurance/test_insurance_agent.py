"""
tests/test_insurance/test_insurance_agent.py
IL-INS-01 | Phase 26 — 15 tests for InsuranceAgent facade.
"""

from __future__ import annotations

import pytest

from services.insurance.insurance_agent import InsuranceAgent


@pytest.fixture
def agent() -> InsuranceAgent:
    return InsuranceAgent()


@pytest.fixture
def quoted_policy_id(agent: InsuranceAgent) -> str:
    result = agent.get_quote("cust-001", "ins-001", "5000.00", 30)
    return result["policy_id"]


@pytest.fixture
def active_policy_id(agent: InsuranceAgent) -> str:
    result = agent.get_quote("cust-001", "ins-001", "5000.00", 30)
    bound = agent.bind_policy(result["policy_id"])
    return bound["policy_id"]


# ── get_quote ─────────────────────────────────────────────────────────────────


def test_get_quote_returns_policy_id(agent: InsuranceAgent) -> None:
    result = agent.get_quote("cust-001", "ins-001", "5000.00", 30)
    assert "policy_id" in result


def test_get_quote_premium_is_string(agent: InsuranceAgent) -> None:
    result = agent.get_quote("cust-001", "ins-001", "5000.00", 30)
    assert isinstance(result["premium"], str)


def test_get_quote_coverage_amount_is_string(agent: InsuranceAgent) -> None:
    result = agent.get_quote("cust-001", "ins-001", "5000.00", 30)
    assert isinstance(result["coverage_amount"], str)


def test_get_quote_status_is_quoted(agent: InsuranceAgent) -> None:
    result = agent.get_quote("cust-001", "ins-001", "5000.00", 30)
    assert result["status"] == "QUOTED"


def test_get_quote_invalid_amount_raises(agent: InsuranceAgent) -> None:
    with pytest.raises(ValueError, match="Invalid coverage_amount"):
        agent.get_quote("cust-001", "ins-001", "not-a-number", 30)


# ── bind_policy ───────────────────────────────────────────────────────────────


def test_bind_policy_status_active(agent: InsuranceAgent, quoted_policy_id: str) -> None:
    result = agent.bind_policy(quoted_policy_id)
    assert result["status"] == "ACTIVE"


def test_bind_policy_returns_policy_id(agent: InsuranceAgent, quoted_policy_id: str) -> None:
    result = agent.bind_policy(quoted_policy_id)
    assert result["policy_id"] == quoted_policy_id


def test_bind_policy_premium_is_string(agent: InsuranceAgent, quoted_policy_id: str) -> None:
    result = agent.bind_policy(quoted_policy_id)
    assert isinstance(result["premium"], str)


# ── file_claim ────────────────────────────────────────────────────────────────


def test_file_claim_small_returns_claim_dict(agent: InsuranceAgent, active_policy_id: str) -> None:
    result = agent.file_claim(active_policy_id, "cust-001", "500.00", "Lost luggage")
    # Should return claim dict with approved status
    assert result.get("status") == "APPROVED"


def test_file_claim_large_returns_hitl(agent: InsuranceAgent, active_policy_id: str) -> None:
    result = agent.file_claim(active_policy_id, "cust-001", "2000.00", "Big claim")
    assert result["status"] == "HITL_REQUIRED"
    assert "claim_id" in result


def test_file_claim_invalid_amount_raises(agent: InsuranceAgent, active_policy_id: str) -> None:
    with pytest.raises(ValueError, match="Invalid claimed_amount"):
        agent.file_claim(active_policy_id, "cust-001", "bad-value", "Test")


# ── list_products ─────────────────────────────────────────────────────────────


def test_list_products_all_returns_four(agent: InsuranceAgent) -> None:
    result = agent.list_products()
    assert len(result["products"]) == 4


def test_list_products_filtered_travel(agent: InsuranceAgent) -> None:
    result = agent.list_products("TRAVEL")
    assert len(result["products"]) == 1
    assert result["products"][0]["coverage_type"] == "TRAVEL"


def test_list_products_base_premium_is_string(agent: InsuranceAgent) -> None:
    result = agent.list_products()
    for p in result["products"]:
        assert isinstance(p["base_premium"], str)
