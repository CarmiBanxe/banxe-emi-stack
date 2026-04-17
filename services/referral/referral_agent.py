"""
services/referral/referral_agent.py — Referral Program Agent facade
IL-REF-01 | Phase 30 | banxe-emi-stack

Orchestrates referral code generation, tracking, fraud detection, reward distribution,
and campaign management. Fraud-blocked referrals always return HITL_REQUIRED (I-27).
Trust Zone: AMBER | Autonomy L2 | L4 HITL for fraud-blocked referrals.
FCA: COBS 4 (financial promotions), PS22/9 (fair value), BCOBS 2.2.
"""

from __future__ import annotations

from services.referral.campaign_manager import CampaignManager
from services.referral.code_generator import CodeGenerator
from services.referral.fraud_detector import FraudDetector
from services.referral.models import (
    InMemoryFraudCheckStore,
    InMemoryReferralCampaignStore,
    InMemoryReferralCodeStore,
    InMemoryReferralRewardStore,
    InMemoryReferralStore,
)
from services.referral.referral_tracker import ReferralTracker
from services.referral.reward_distributor import RewardDistributor


class ReferralAgent:
    """
    Central Referral Program orchestrator.
    Fraud-blocked referrals return HITL_REQUIRED — never auto-approve (I-27).
    Autonomy L2. L4 HITL for fraud-blocked reward distribution.
    """

    def __init__(self) -> None:
        # Shared stores
        self._code_store = InMemoryReferralCodeStore()
        self._referral_store = InMemoryReferralStore()
        self._reward_store = InMemoryReferralRewardStore()
        self._campaign_store = InMemoryReferralCampaignStore()
        self._fraud_store = InMemoryFraudCheckStore()

        self._code_generator = CodeGenerator(code_store=self._code_store)
        self._tracker = ReferralTracker(
            referral_store=self._referral_store,
            code_store=self._code_store,
        )
        self._reward_distributor = RewardDistributor(
            reward_store=self._reward_store,
            referral_store=self._referral_store,
            campaign_store=self._campaign_store,
        )
        self._fraud_detector = FraudDetector(fraud_store=self._fraud_store)
        self._campaign_manager = CampaignManager(campaign_store=self._campaign_store)

    def generate_code(
        self,
        customer_id: str,
        campaign_id: str = "camp-default",
        vanity_suffix: str = "",
    ) -> dict:
        """Generate a unique referral code for a customer."""
        code = self._code_generator.generate_code(customer_id, campaign_id, vanity_suffix)
        return {
            "code_id": code.code_id,
            "customer_id": code.customer_id,
            "code": code.code,
            "campaign_id": code.campaign_id,
            "is_vanity": code.is_vanity,
            "created_at": code.created_at.isoformat(),
        }

    def track_referral(
        self,
        referee_id: str,
        code_str: str,
        ip_address: str = "0.0.0.0",  # noqa: S104  # nosec B104
        device_id: str = "",
    ) -> dict:
        """Register a referral. Runs fraud check after tracking."""
        result = self._tracker.track_referral(referee_id, code_str)

        # Run fraud check immediately after tracking
        referral_id = result["referral_id"]
        referrer_id = result["referrer_id"]
        fraud_check = self._fraud_detector.check_fraud(
            referral_id=referral_id,
            referrer_id=referrer_id,
            referee_id=referee_id,
            ip_address=ip_address,
            device_id=device_id,
        )
        result["fraud_flagged"] = fraud_check.is_fraudulent

        return result

    def advance_referral(self, referral_id: str, new_status_str: str) -> dict:
        """Advance referral status through lifecycle."""
        return self._tracker.advance_status(referral_id, new_status_str)

    def distribute_rewards(
        self,
        referral_id: str,
        ip_address: str = "0.0.0.0",  # noqa: S104  # nosec B104
    ) -> dict:
        """Distribute rewards for a QUALIFIED referral.

        Returns HITL_REQUIRED if fraud-blocked (I-27).
        """
        if self._fraud_detector.is_fraud_blocked(referral_id):
            return {
                "status": "HITL_REQUIRED",
                "referral_id": referral_id,
                "reason": "Fraud-blocked referral requires Compliance Officer review (I-27)",
            }
        return self._reward_distributor.distribute_rewards(referral_id)

    def get_referral_status(self, referral_id: str) -> dict:
        """Get current status and details of a referral."""
        return self._tracker.get_referral_status(referral_id)

    def get_campaign_stats(self, campaign_id: str) -> dict:
        """Return campaign budget and statistics."""
        return self._campaign_manager.get_campaign_stats(campaign_id)

    def list_active_campaigns(self) -> dict:
        """List all active referral campaigns."""
        return self._campaign_manager.list_active_campaigns()

    def get_reward_summary(self, customer_id: str) -> dict:
        """Return total earned/pending/paid rewards for a customer."""
        return self._reward_distributor.get_reward_summary(customer_id)

    def check_fraud(
        self,
        referral_id: str,
        referrer_id: str,
        referee_id: str,
        ip_address: str,
        device_id: str = "",
    ) -> dict:
        """Run a fraud check and return the result."""
        return self._fraud_detector.get_fraud_report(referral_id)
