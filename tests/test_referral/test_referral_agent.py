"""
tests/test_referral/test_referral_agent.py — Unit tests for ReferralAgent facade
IL-REF-01 | Phase 30 | banxe-emi-stack
"""

from __future__ import annotations

import pytest

from services.referral.referral_agent import ReferralAgent


@pytest.fixture()
def agent() -> ReferralAgent:
    return ReferralAgent()


def _setup_qualified_referral(agent: ReferralAgent) -> tuple[str, str]:
    """Create a code, track a referral, advance to QUALIFIED. Returns (referral_id, code)."""
    code_result = agent.generate_code("referrer-setup", campaign_id="camp-default")
    code = code_result["code"]
    track_result = agent.track_referral("referee-setup", code, ip_address="192.168.1.100")
    referral_id = track_result["referral_id"]
    agent.advance_referral(referral_id, "REGISTERED")
    agent.advance_referral(referral_id, "KYC_COMPLETE")
    agent.advance_referral(referral_id, "QUALIFIED")
    return referral_id, code


# ── generate_code ──────────────────────────────────────────────────────────


def test_generate_code_returns_dict(agent: ReferralAgent) -> None:
    result = agent.generate_code("cust-1")
    assert isinstance(result, dict)


def test_generate_code_has_code_field(agent: ReferralAgent) -> None:
    result = agent.generate_code("cust-2")
    assert "code" in result
    assert len(result["code"]) == 8


def test_generate_code_has_customer_id(agent: ReferralAgent) -> None:
    result = agent.generate_code("cust-3")
    assert result["customer_id"] == "cust-3"


def test_generate_code_vanity(agent: ReferralAgent) -> None:
    result = agent.generate_code("vip-cust", vanity_suffix="JOHN")
    assert result["code"].startswith("BANXE")
    assert result["is_vanity"] is True


def test_generate_code_default_campaign(agent: ReferralAgent) -> None:
    result = agent.generate_code("cust-4")
    assert result["campaign_id"] == "camp-default"


# ── track_referral ─────────────────────────────────────────────────────────


def test_track_referral_success(agent: ReferralAgent) -> None:
    code_result = agent.generate_code("track-referrer-1")
    code = code_result["code"]
    result = agent.track_referral("track-referee-1", code, ip_address="1.2.3.4")
    assert result["status"] == "INVITED"


def test_track_referral_has_fraud_flagged_field(agent: ReferralAgent) -> None:
    code_result = agent.generate_code("track-referrer-2")
    code = code_result["code"]
    result = agent.track_referral("track-referee-2", code, ip_address="1.2.3.4")
    assert "fraud_flagged" in result


def test_track_referral_clean_not_fraud_flagged(agent: ReferralAgent) -> None:
    code_result = agent.generate_code("track-referrer-3")
    code = code_result["code"]
    result = agent.track_referral("track-referee-3", code, ip_address="2.3.4.5")
    assert result["fraud_flagged"] is False


def test_track_referral_invalid_code_raises(agent: ReferralAgent) -> None:
    with pytest.raises(ValueError):
        agent.track_referral("some-cust", "BADCODE1", ip_address="1.1.1.1")


# ── advance_referral ───────────────────────────────────────────────────────


def test_advance_referral_invited_to_registered(agent: ReferralAgent) -> None:
    code_result = agent.generate_code("adv-referrer-1")
    track = agent.track_referral("adv-referee-1", code_result["code"], ip_address="1.1.1.1")
    result = agent.advance_referral(track["referral_id"], "REGISTERED")
    assert result["status"] == "REGISTERED"


def test_advance_referral_not_found_raises(agent: ReferralAgent) -> None:
    with pytest.raises(ValueError):
        agent.advance_referral("nonexistent-ref-id", "REGISTERED")


# ── distribute_rewards ─────────────────────────────────────────────────────


def test_distribute_rewards_for_qualified_referral(agent: ReferralAgent) -> None:
    referral_id, _ = _setup_qualified_referral(agent)
    result = agent.distribute_rewards(referral_id)
    assert result["referral_id"] == referral_id
    assert result["status"] == "PENDING"


def test_distribute_rewards_creates_two_rewards(agent: ReferralAgent) -> None:
    referral_id, _ = _setup_qualified_referral(agent)
    result = agent.distribute_rewards(referral_id)
    assert len(result["reward_ids"]) == 2


def test_distribute_rewards_fraud_blocked_returns_hitl(agent: ReferralAgent) -> None:
    # Self-referral triggers fraud
    code_result = agent.generate_code("self-ref-cust")
    code = code_result["code"]
    # Manually force fraud check by using same ID
    from decimal import Decimal

    from services.referral.models import FraudCheck, FraudReason

    # Track a normal referral, then manually mark it as fraud
    track = agent.track_referral("fraud-referee-1", code, ip_address="9.9.9.9")
    referral_id = track["referral_id"]

    # Directly inject a fraud check for the referral
    from datetime import UTC, datetime
    import uuid

    fraud_check = FraudCheck(
        check_id=str(uuid.uuid4()),
        referral_id=referral_id,
        fraud_reason=FraudReason.SELF_REFERRAL,
        is_fraudulent=True,
        confidence_score=Decimal("1.0"),
        checked_at=datetime.now(UTC),
    )
    agent._fraud_detector._store.save(fraud_check)

    # Advance to QUALIFIED
    agent.advance_referral(referral_id, "REGISTERED")
    agent.advance_referral(referral_id, "KYC_COMPLETE")
    agent.advance_referral(referral_id, "QUALIFIED")

    result = agent.distribute_rewards(referral_id)
    assert result["status"] == "HITL_REQUIRED"


def test_distribute_rewards_hitl_contains_referral_id(agent: ReferralAgent) -> None:
    """HITL response must include referral_id for HITL routing (I-27)."""
    code_result = agent.generate_code("hitl-ref-cust")
    code = code_result["code"]
    track = agent.track_referral("hitl-referee-1", code, ip_address="9.8.7.6")
    referral_id = track["referral_id"]

    from datetime import UTC, datetime
    from decimal import Decimal
    import uuid

    from services.referral.models import FraudCheck, FraudReason

    fraud_check = FraudCheck(
        check_id=str(uuid.uuid4()),
        referral_id=referral_id,
        fraud_reason=FraudReason.VELOCITY_ABUSE,
        is_fraudulent=True,
        confidence_score=Decimal("0.9"),
        checked_at=datetime.now(UTC),
    )
    agent._fraud_detector._store.save(fraud_check)
    agent.advance_referral(referral_id, "REGISTERED")
    agent.advance_referral(referral_id, "KYC_COMPLETE")
    agent.advance_referral(referral_id, "QUALIFIED")
    result = agent.distribute_rewards(referral_id)
    assert result["referral_id"] == referral_id


# ── get_referral_status ────────────────────────────────────────────────────


def test_get_referral_status_returns_status(agent: ReferralAgent) -> None:
    code_result = agent.generate_code("status-referrer")
    track = agent.track_referral("status-referee", code_result["code"], ip_address="1.1.1.1")
    result = agent.get_referral_status(track["referral_id"])
    assert result["status"] == "INVITED"


# ── get_campaign_stats ─────────────────────────────────────────────────────


def test_get_campaign_stats_default(agent: ReferralAgent) -> None:
    result = agent.get_campaign_stats("camp-default")
    assert result["campaign_id"] == "camp-default"
    assert "remaining_budget" in result


# ── list_active_campaigns ──────────────────────────────────────────────────


def test_list_active_campaigns_returns_dict(agent: ReferralAgent) -> None:
    result = agent.list_active_campaigns()
    assert "campaigns" in result


def test_list_active_campaigns_includes_default(agent: ReferralAgent) -> None:
    result = agent.list_active_campaigns()
    ids = [c["campaign_id"] for c in result["campaigns"]]
    assert "camp-default" in ids


# ── get_reward_summary ─────────────────────────────────────────────────────


def test_get_reward_summary_empty_customer(agent: ReferralAgent) -> None:
    result = agent.get_reward_summary("no-reward-cust")
    assert result["total_earned"] == "0"
    assert result["reward_count"] == 0


def test_get_reward_summary_after_distribution(agent: ReferralAgent) -> None:
    referral_id, _ = _setup_qualified_referral(agent)
    agent.distribute_rewards(referral_id)
    result = agent.get_reward_summary("referrer-setup")
    assert result["total_earned"] == "25.00"


# ── check_fraud ────────────────────────────────────────────────────────────


def test_check_fraud_returns_report(agent: ReferralAgent) -> None:
    code_result = agent.generate_code("fraud-check-referrer")
    track = agent.track_referral("fraud-check-referee", code_result["code"], ip_address="4.5.6.7")
    result = agent.check_fraud(
        referral_id=track["referral_id"],
        referrer_id="fraud-check-referrer",
        referee_id="fraud-check-referee",
        ip_address="4.5.6.7",
    )
    assert "checked" in result
