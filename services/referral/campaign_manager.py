"""
services/referral/campaign_manager.py — Referral campaign lifecycle
IL-REF-01 | Phase 30 | banxe-emi-stack

Manages referral campaign lifecycle: DRAFT → ACTIVE → PAUSED → ENDED.
Budget tracking and campaign statistics. All reward amounts Decimal (I-01).
FCA: COBS 4 (financial promotions — campaigns are regulated marketing).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.referral.models import (
    CampaignStatus,
    InMemoryReferralCampaignStore,
    ReferralCampaign,
    ReferralCampaignStorePort,
)


class CampaignManager:
    """Referral campaign lifecycle: create, activate, pause, end, and stats."""

    def __init__(self, campaign_store: ReferralCampaignStorePort | None = None) -> None:
        self._store = campaign_store or InMemoryReferralCampaignStore()

    def create_campaign(
        self,
        name: str,
        referrer_reward_str: str,
        referee_reward_str: str,
        total_budget_str: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict:
        """Create a new DRAFT campaign. Validates amounts > 0.

        Raises:
            ValueError: invalid amounts
        """
        referrer_reward = Decimal(referrer_reward_str)
        referee_reward = Decimal(referee_reward_str)
        total_budget = Decimal(total_budget_str)

        if referrer_reward <= Decimal("0"):
            raise ValueError(f"referrer_reward must be > 0, got {referrer_reward_str}")
        if referee_reward <= Decimal("0"):
            raise ValueError(f"referee_reward must be > 0, got {referee_reward_str}")
        if total_budget <= Decimal("0"):
            raise ValueError(f"total_budget must be > 0, got {total_budget_str}")

        now = datetime.now(UTC)
        campaign = ReferralCampaign(
            campaign_id=str(uuid.uuid4()),
            name=name,
            referrer_reward=referrer_reward,
            referee_reward=referee_reward,
            total_budget=total_budget,
            spent_budget=Decimal("0"),
            status=CampaignStatus.DRAFT,
            start_date=start_date or now,
            created_at=now,
            end_date=end_date,
        )
        self._store.save(campaign)

        return {
            "campaign_id": campaign.campaign_id,
            "name": campaign.name,
            "referrer_reward": str(campaign.referrer_reward),
            "referee_reward": str(campaign.referee_reward),
            "total_budget": str(campaign.total_budget),
            "status": CampaignStatus.DRAFT.value,
        }

    def activate_campaign(self, campaign_id: str) -> dict:
        """Transition campaign from DRAFT → ACTIVE."""
        campaign = self._store.get(campaign_id)
        if campaign is None:
            raise ValueError(f"Campaign not found: {campaign_id}")
        if campaign.status != CampaignStatus.DRAFT:
            raise ValueError(f"Can only activate DRAFT campaigns, current: {campaign.status.value}")
        updated = replace(campaign, status=CampaignStatus.ACTIVE)
        self._store.update(updated)
        return {"campaign_id": campaign_id, "status": CampaignStatus.ACTIVE.value}

    def pause_campaign(self, campaign_id: str) -> dict:
        """Transition campaign from ACTIVE → PAUSED."""
        campaign = self._store.get(campaign_id)
        if campaign is None:
            raise ValueError(f"Campaign not found: {campaign_id}")
        if campaign.status != CampaignStatus.ACTIVE:
            raise ValueError(f"Can only pause ACTIVE campaigns, current: {campaign.status.value}")
        updated = replace(campaign, status=CampaignStatus.PAUSED)
        self._store.update(updated)
        return {"campaign_id": campaign_id, "status": CampaignStatus.PAUSED.value}

    def end_campaign(self, campaign_id: str) -> dict:
        """Transition campaign to ENDED from any non-ended state."""
        campaign = self._store.get(campaign_id)
        if campaign is None:
            raise ValueError(f"Campaign not found: {campaign_id}")
        if campaign.status == CampaignStatus.ENDED:
            raise ValueError(f"Campaign already ended: {campaign_id}")
        updated = replace(campaign, status=CampaignStatus.ENDED, end_date=datetime.now(UTC))
        self._store.update(updated)
        return {"campaign_id": campaign_id, "status": CampaignStatus.ENDED.value}

    def get_campaign_stats(self, campaign_id: str) -> dict:
        """Return campaign statistics including budget utilisation."""
        campaign = self._store.get(campaign_id)
        if campaign is None:
            raise ValueError(f"Campaign not found: {campaign_id}")
        remaining = campaign.total_budget - campaign.spent_budget
        return {
            "campaign_id": campaign.campaign_id,
            "name": campaign.name,
            "status": campaign.status.value,
            "referrer_reward": str(campaign.referrer_reward),
            "referee_reward": str(campaign.referee_reward),
            "total_budget": str(campaign.total_budget),
            "spent_budget": str(campaign.spent_budget),
            "remaining_budget": str(remaining),
        }

    def list_active_campaigns(self) -> dict:
        """List all currently ACTIVE campaigns."""
        campaigns = self._store.list_active()
        return {
            "campaigns": [
                {
                    "campaign_id": c.campaign_id,
                    "name": c.name,
                    "referrer_reward": str(c.referrer_reward),
                    "referee_reward": str(c.referee_reward),
                    "remaining_budget": str(c.total_budget - c.spent_budget),
                    "status": c.status.value,
                }
                for c in campaigns
            ]
        }
