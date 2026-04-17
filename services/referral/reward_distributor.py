"""
services/referral/reward_distributor.py — Bi-directional reward distribution
IL-REF-01 | Phase 30 | banxe-emi-stack

Distributes referral rewards to both referrer and referee when referral QUALIFIES.
Validates campaign budget before distributing. All amounts Decimal (I-01).
FCA: PS22/9 (fair value), COBS 4 (financial promotions).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.referral.models import (
    InMemoryReferralCampaignStore,
    InMemoryReferralRewardStore,
    InMemoryReferralStore,
    ReferralCampaignStorePort,
    ReferralReward,
    ReferralRewardStorePort,
    ReferralStatus,
    ReferralStorePort,
    RewardStatus,
)


class RewardDistributor:
    """Distributes bi-directional rewards (referrer + referee) when a referral qualifies."""

    def __init__(
        self,
        reward_store: ReferralRewardStorePort | None = None,
        referral_store: ReferralStorePort | None = None,
        campaign_store: ReferralCampaignStorePort | None = None,
    ) -> None:
        self._reward_store = reward_store or InMemoryReferralRewardStore()
        self._referral_store = referral_store or InMemoryReferralStore()
        self._campaign_store = campaign_store or InMemoryReferralCampaignStore()

    def distribute_rewards(self, referral_id: str) -> dict:
        """Create pending rewards for referrer and referee.

        Referral must be QUALIFIED. Campaign must be ACTIVE with budget.

        Raises:
            ValueError: referral not QUALIFIED, campaign not found/active, budget exhausted
        """
        referral = self._referral_store.get(referral_id)
        if referral is None:
            raise ValueError(f"Referral not found: {referral_id}")
        if referral.status != ReferralStatus.QUALIFIED:
            raise ValueError(f"Referral must be QUALIFIED, current: {referral.status.value}")

        campaign = self._campaign_store.get(referral.campaign_id)
        if campaign is None:
            raise ValueError(f"Campaign not found: {referral.campaign_id}")
        from services.referral.models import CampaignStatus  # noqa: PLC0415

        if campaign.status != CampaignStatus.ACTIVE:
            raise ValueError(f"Campaign not active: {campaign.status.value}")

        total_payout = campaign.referrer_reward + campaign.referee_reward
        remaining = campaign.total_budget - campaign.spent_budget
        if remaining < total_payout:
            raise ValueError(
                f"Campaign budget exhausted: remaining={remaining}, needed={total_payout}"
            )

        now = datetime.now(UTC)

        referrer_reward = ReferralReward(
            reward_id=str(uuid.uuid4()),
            referral_id=referral_id,
            recipient_id=referral.referrer_id,
            amount=campaign.referrer_reward,
            reward_type="referrer",
            status=RewardStatus.PENDING,
            created_at=now,
        )
        referee_reward = ReferralReward(
            reward_id=str(uuid.uuid4()),
            referral_id=referral_id,
            recipient_id=referral.referee_id,
            amount=campaign.referee_reward,
            reward_type="referee",
            status=RewardStatus.PENDING,
            created_at=now,
        )
        self._reward_store.save(referrer_reward)
        self._reward_store.save(referee_reward)

        # Update campaign spent budget
        updated_campaign = replace(campaign, spent_budget=campaign.spent_budget + total_payout)
        self._campaign_store.update(updated_campaign)

        # Advance referral to REWARDED
        updated_referral = replace(referral, status=ReferralStatus.REWARDED, rewarded_at=now)
        self._referral_store.update(updated_referral)

        return {
            "referral_id": referral_id,
            "referrer_reward": str(campaign.referrer_reward),
            "referee_reward": str(campaign.referee_reward),
            "status": RewardStatus.PENDING.value,
            "reward_ids": [referrer_reward.reward_id, referee_reward.reward_id],
        }

    def approve_reward(self, reward_id: str) -> dict:
        """Advance reward from PENDING → APPROVED → PAID."""
        reward = self._reward_store.get(reward_id)
        if reward is None:
            raise ValueError(f"Reward not found: {reward_id}")
        if reward.status == RewardStatus.PENDING:
            updated = replace(reward, status=RewardStatus.APPROVED)
        elif reward.status == RewardStatus.APPROVED:
            updated = replace(reward, status=RewardStatus.PAID, paid_at=datetime.now(UTC))
        else:
            raise ValueError(f"Cannot approve reward in status: {reward.status.value}")
        self._reward_store.update(updated)
        return {
            "reward_id": reward_id,
            "recipient_id": updated.recipient_id,
            "amount": str(updated.amount),
            "status": updated.status.value,
        }

    def get_reward_summary(self, customer_id: str) -> dict:
        """Total earned, pending, and paid rewards for a customer (all Decimal, as strings)."""
        rewards = self._reward_store.list_by_recipient(customer_id)
        total_earned = sum((r.amount for r in rewards), Decimal("0"))
        total_pending = sum(
            (r.amount for r in rewards if r.status == RewardStatus.PENDING), Decimal("0")
        )
        total_paid = sum((r.amount for r in rewards if r.status == RewardStatus.PAID), Decimal("0"))
        return {
            "customer_id": customer_id,
            "total_earned": str(total_earned),
            "total_pending": str(total_pending),
            "total_paid": str(total_paid),
            "reward_count": len(rewards),
        }
