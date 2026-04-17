"""
services/referral/referral_tracker.py — Referral lifecycle tracking
IL-REF-01 | Phase 30 | banxe-emi-stack

Tracks referral chain: INVITED → REGISTERED → KYC_COMPLETE → QUALIFIED → REWARDED.
Self-referral detection at entry point.
FCA: COBS 4 (financial promotions compliance), BCOBS 2.2 (communications).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import uuid

from services.referral.models import (
    InMemoryReferralCodeStore,
    InMemoryReferralStore,
    Referral,
    ReferralCodeStorePort,
    ReferralStatus,
    ReferralStorePort,
)

_VALID_TRANSITIONS: dict[ReferralStatus, list[ReferralStatus]] = {
    ReferralStatus.INVITED: [ReferralStatus.REGISTERED, ReferralStatus.FRAUDULENT],
    ReferralStatus.REGISTERED: [ReferralStatus.KYC_COMPLETE, ReferralStatus.FRAUDULENT],
    ReferralStatus.KYC_COMPLETE: [ReferralStatus.QUALIFIED, ReferralStatus.FRAUDULENT],
    ReferralStatus.QUALIFIED: [ReferralStatus.REWARDED, ReferralStatus.FRAUDULENT],
    ReferralStatus.REWARDED: [],
    ReferralStatus.FRAUDULENT: [],
}


class ReferralTracker:
    """Tracks referral lifecycle from invite to reward."""

    def __init__(
        self,
        referral_store: ReferralStorePort | None = None,
        code_store: ReferralCodeStorePort | None = None,
    ) -> None:
        self._referral_store = referral_store or InMemoryReferralStore()
        self._code_store = code_store or InMemoryReferralCodeStore()

    def track_referral(self, referee_id: str, code_str: str) -> dict:
        """Register a referral using a referral code.

        Validates code, checks self-referral, checks duplicate.
        Returns {"referral_id", "referrer_id", "referee_id", "status": "INVITED"}.

        Raises:
            ValueError: self_referral, invalid_code, already_referred
        """
        ref_code = self._code_store.get_by_code(code_str)
        if ref_code is None:
            raise ValueError(f"Invalid referral code: {code_str}")

        referrer_id = ref_code.customer_id

        if referrer_id == referee_id:
            raise ValueError("self_referral: cannot refer yourself")

        if ref_code.used_count >= ref_code.max_uses:
            raise ValueError(f"Referral code exhausted: {code_str}")

        existing = self._referral_store.list_by_referee(referee_id)
        if existing:
            raise ValueError(f"Customer {referee_id} already referred")

        now = datetime.now(UTC)
        referral = Referral(
            referral_id=str(uuid.uuid4()),
            referrer_id=referrer_id,
            referee_id=referee_id,
            code=code_str,
            campaign_id=ref_code.campaign_id,
            status=ReferralStatus.INVITED,
            created_at=now,
        )
        self._referral_store.save(referral)

        # Increment code usage
        updated_code = replace(ref_code, used_count=ref_code.used_count + 1)
        self._code_store.update(updated_code)

        return {
            "referral_id": referral.referral_id,
            "referrer_id": referrer_id,
            "referee_id": referee_id,
            "status": ReferralStatus.INVITED.value,
        }

    def advance_status(self, referral_id: str, new_status_str: str) -> dict:
        """Advance referral status through the lifecycle.

        Valid: INVITED→REGISTERED, REGISTERED→KYC_COMPLETE, KYC_COMPLETE→QUALIFIED.
        QUALIFIED→REWARDED only via reward_distributor.

        Raises:
            ValueError: invalid transition or referral not found
        """
        referral = self._referral_store.get(referral_id)
        if referral is None:
            raise ValueError(f"Referral not found: {referral_id}")

        new_status = ReferralStatus(new_status_str)
        allowed = _VALID_TRANSITIONS.get(referral.status, [])
        if new_status not in allowed:
            raise ValueError(f"Invalid transition {referral.status.value} → {new_status_str}")

        now = datetime.now(UTC)
        qualified_at = referral.qualified_at
        if new_status == ReferralStatus.QUALIFIED:
            qualified_at = now

        updated = replace(referral, status=new_status, qualified_at=qualified_at)
        self._referral_store.update(updated)

        return {
            "referral_id": referral_id,
            "referrer_id": referral.referrer_id,
            "referee_id": referral.referee_id,
            "status": new_status_str,
            "qualified_at": qualified_at.isoformat() if qualified_at else None,
        }

    def get_referral_status(self, referral_id: str) -> dict:
        """Get current status of a referral."""
        referral = self._referral_store.get(referral_id)
        if referral is None:
            raise ValueError(f"Referral not found: {referral_id}")
        return {
            "referral_id": referral.referral_id,
            "referrer_id": referral.referrer_id,
            "referee_id": referral.referee_id,
            "code": referral.code,
            "status": referral.status.value,
            "created_at": referral.created_at.isoformat(),
            "qualified_at": referral.qualified_at.isoformat() if referral.qualified_at else None,
            "rewarded_at": referral.rewarded_at.isoformat() if referral.rewarded_at else None,
        }

    def list_referrals_by_referrer(self, referrer_id: str) -> dict:
        """List all referrals made by a referrer."""
        referrals = self._referral_store.list_by_referrer(referrer_id)
        return {
            "referrer_id": referrer_id,
            "referrals": [
                {
                    "referral_id": r.referral_id,
                    "referee_id": r.referee_id,
                    "status": r.status.value,
                    "created_at": r.created_at.isoformat(),
                }
                for r in referrals
            ],
        }
