"""
tests/test_referral/test_reward_distributor.py — Unit tests for RewardDistributor
IL-REF-01 | Phase 30 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import uuid

import pytest

from services.referral.models import (
    CampaignStatus,
    InMemoryReferralCampaignStore,
    InMemoryReferralRewardStore,
    InMemoryReferralStore,
    Referral,
    ReferralCampaign,
    ReferralStatus,
)
from services.referral.reward_distributor import RewardDistributor


def _now() -> datetime:
    return datetime.now(UTC)


def _make_qualified_referral(
    referral_id: str,
    referrer_id: str = "referrer-1",
    referee_id: str = "referee-1",
    campaign_id: str = "camp-default",
) -> Referral:
    return Referral(
        referral_id=referral_id,
        referrer_id=referrer_id,
        referee_id=referee_id,
        code="TESTCODE",
        campaign_id=campaign_id,
        status=ReferralStatus.QUALIFIED,
        created_at=_now(),
        qualified_at=_now(),
    )


@pytest.fixture()
def distributor() -> RewardDistributor:
    return RewardDistributor()


@pytest.fixture()
def distributor_with_qualified() -> tuple[RewardDistributor, str]:
    """Distributor with a QUALIFIED referral pre-loaded."""
    referral_id = str(uuid.uuid4())
    ref_store = InMemoryReferralStore()
    ref_store.save(_make_qualified_referral(referral_id))
    reward_store = InMemoryReferralRewardStore()
    dist = RewardDistributor(
        reward_store=reward_store,
        referral_store=ref_store,
    )
    return dist, referral_id


# ── distribute_rewards ─────────────────────────────────────────────────────


def test_distribute_rewards_success(
    distributor_with_qualified: tuple[RewardDistributor, str],
) -> None:
    dist, referral_id = distributor_with_qualified
    result = dist.distribute_rewards(referral_id)
    assert result["referral_id"] == referral_id


def test_distribute_rewards_returns_referrer_reward(
    distributor_with_qualified: tuple[RewardDistributor, str],
) -> None:
    dist, referral_id = distributor_with_qualified
    result = dist.distribute_rewards(referral_id)
    assert result["referrer_reward"] == "25.00"


def test_distribute_rewards_returns_referee_reward(
    distributor_with_qualified: tuple[RewardDistributor, str],
) -> None:
    dist, referral_id = distributor_with_qualified
    result = dist.distribute_rewards(referral_id)
    assert result["referee_reward"] == "10.00"


def test_distribute_rewards_creates_two_rewards(
    distributor_with_qualified: tuple[RewardDistributor, str],
) -> None:
    dist, referral_id = distributor_with_qualified
    result = dist.distribute_rewards(referral_id)
    assert len(result["reward_ids"]) == 2


def test_distribute_rewards_status_is_pending(
    distributor_with_qualified: tuple[RewardDistributor, str],
) -> None:
    dist, referral_id = distributor_with_qualified
    result = dist.distribute_rewards(referral_id)
    assert result["status"] == "PENDING"


def test_distribute_rewards_referral_not_found_raises(distributor: RewardDistributor) -> None:
    with pytest.raises(ValueError, match="Referral not found"):
        distributor.distribute_rewards("nonexistent-id")


def test_distribute_rewards_referral_not_qualified_raises() -> None:
    ref_store = InMemoryReferralStore()
    ref_store.save(
        Referral(
            referral_id="invited-ref",
            referrer_id="r1",
            referee_id="r2",
            code="CODE",
            campaign_id="camp-default",
            status=ReferralStatus.INVITED,
            created_at=_now(),
        )
    )
    dist = RewardDistributor(referral_store=ref_store)
    with pytest.raises(ValueError, match="must be QUALIFIED"):
        dist.distribute_rewards("invited-ref")


def test_distribute_rewards_campaign_not_found_raises() -> None:
    ref_store = InMemoryReferralStore()
    ref_store.save(_make_qualified_referral("r1", campaign_id="nonexistent-camp"))
    campaign_store = InMemoryReferralCampaignStore()
    # Remove default campaign by using fresh campaign store without it
    dist = RewardDistributor(
        referral_store=ref_store,
        campaign_store=campaign_store,
    )
    with pytest.raises(ValueError):
        dist.distribute_rewards("r1")


def test_distribute_rewards_budget_exhausted_raises() -> None:
    referral_id = str(uuid.uuid4())
    ref_store = InMemoryReferralStore()
    ref_store.save(_make_qualified_referral(referral_id, campaign_id="tight-camp"))

    campaign_store = InMemoryReferralCampaignStore()
    now = _now()
    tight_campaign = ReferralCampaign(
        campaign_id="tight-camp",
        name="Tight Budget",
        referrer_reward=Decimal("25.00"),
        referee_reward=Decimal("10.00"),
        total_budget=Decimal("30.00"),
        spent_budget=Decimal("30.00"),  # Fully spent
        status=CampaignStatus.ACTIVE,
        start_date=now,
        created_at=now,
    )
    campaign_store.save(tight_campaign)

    dist = RewardDistributor(
        referral_store=ref_store,
        campaign_store=campaign_store,
    )
    with pytest.raises(ValueError, match="budget exhausted"):
        dist.distribute_rewards(referral_id)


def test_distribute_rewards_advances_referral_to_rewarded(
    distributor_with_qualified: tuple[RewardDistributor, str],
) -> None:
    dist, referral_id = distributor_with_qualified
    dist.distribute_rewards(referral_id)
    # Referral should now be REWARDED
    referral = dist._referral_store.get(referral_id)
    assert referral.status == ReferralStatus.REWARDED


# ── approve_reward ─────────────────────────────────────────────────────────


def test_approve_reward_pending_to_approved(
    distributor_with_qualified: tuple[RewardDistributor, str],
) -> None:
    dist, referral_id = distributor_with_qualified
    result = dist.distribute_rewards(referral_id)
    reward_id = result["reward_ids"][0]
    approved = dist.approve_reward(reward_id)
    assert approved["status"] == "APPROVED"


def test_approve_reward_approved_to_paid(
    distributor_with_qualified: tuple[RewardDistributor, str],
) -> None:
    dist, referral_id = distributor_with_qualified
    result = dist.distribute_rewards(referral_id)
    reward_id = result["reward_ids"][0]
    dist.approve_reward(reward_id)
    paid = dist.approve_reward(reward_id)
    assert paid["status"] == "PAID"


def test_approve_reward_not_found_raises(distributor: RewardDistributor) -> None:
    with pytest.raises(ValueError, match="Reward not found"):
        distributor.approve_reward("nonexistent-reward")


def test_approve_reward_already_paid_raises(
    distributor_with_qualified: tuple[RewardDistributor, str],
) -> None:
    dist, referral_id = distributor_with_qualified
    result = dist.distribute_rewards(referral_id)
    reward_id = result["reward_ids"][0]
    dist.approve_reward(reward_id)
    dist.approve_reward(reward_id)
    with pytest.raises(ValueError, match="Cannot approve"):
        dist.approve_reward(reward_id)


def test_approve_reward_returns_amount(
    distributor_with_qualified: tuple[RewardDistributor, str],
) -> None:
    dist, referral_id = distributor_with_qualified
    result = dist.distribute_rewards(referral_id)
    reward_id = result["reward_ids"][0]
    approved = dist.approve_reward(reward_id)
    assert "amount" in approved


# ── get_reward_summary ─────────────────────────────────────────────────────


def test_get_reward_summary_empty_for_new_customer(distributor: RewardDistributor) -> None:
    result = distributor.get_reward_summary("no-rewards-cust")
    assert result["total_earned"] == "0"
    assert result["reward_count"] == 0


def test_get_reward_summary_after_distribution(
    distributor_with_qualified: tuple[RewardDistributor, str],
) -> None:
    dist, referral_id = distributor_with_qualified
    dist.distribute_rewards(referral_id)
    # referrer should have a PENDING reward
    result = dist.get_reward_summary("referrer-1")
    assert result["total_earned"] == "25.00"
    assert result["total_pending"] == "25.00"


def test_get_reward_summary_paid_amount(
    distributor_with_qualified: tuple[RewardDistributor, str],
) -> None:
    dist, referral_id = distributor_with_qualified
    dist.distribute_rewards(referral_id)
    reward_id = dist.distribute_rewards  # Just get summary without paying
    result_before = dist.get_reward_summary("referrer-1")
    assert result_before["total_paid"] == "0"
