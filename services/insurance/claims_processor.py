"""
services/insurance/claims_processor.py
IL-INS-01 | Phase 26

Claims lifecycle: FILED → UNDER_ASSESSMENT → APPROVED/DECLINED → PAID.
HITL gate: approve_claim returns HITL_REQUIRED for amounts >£1000 (I-27).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.insurance.models import (
    Claim,
    ClaimStatus,
    ClaimStorePort,
    InMemoryClaimStore,
    InMemoryPolicyStore,
    PolicyStatus,
    PolicyStorePort,
)

_HITL_THRESHOLD = Decimal("1000.00")


class ClaimsProcessor:
    def __init__(
        self,
        policy_store: PolicyStorePort | None = None,
        claim_store: ClaimStorePort | None = None,
    ) -> None:
        self._policy_store: PolicyStorePort = policy_store or InMemoryPolicyStore()
        self._claim_store: ClaimStorePort = claim_store or InMemoryClaimStore()

    def file_claim(
        self,
        policy_id: str,
        customer_id: str,
        claimed_amount: Decimal,
        description: str,
        evidence_urls: list[str],
    ) -> Claim:
        policy = self._policy_store.get(policy_id)
        if policy is None or policy.status != PolicyStatus.ACTIVE:
            raise ValueError(f"Policy {policy_id} is not ACTIVE — cannot file claim")
        claim = Claim(
            claim_id=str(uuid.uuid4()),
            policy_id=policy_id,
            customer_id=customer_id,
            status=ClaimStatus.FILED,
            claimed_amount=claimed_amount,
            approved_amount=None,
            filed_at=datetime.now(UTC),
            description=description,
            evidence_urls=evidence_urls,
        )
        self._claim_store.save(claim)
        return claim

    def assess_claim(self, claim_id: str) -> Claim:
        claim = self._claim_store.get(claim_id)
        if claim is None:
            raise ValueError(f"Claim not found: {claim_id}")
        if claim.status != ClaimStatus.FILED:
            raise ValueError(f"Claim {claim_id} must be FILED to assess, got {claim.status}")
        return self._claim_store.update_status(claim_id, ClaimStatus.UNDER_ASSESSMENT, None)

    def approve_claim(self, claim_id: str, approved_amount: Decimal, actor: str) -> dict:
        """Returns HITL_REQUIRED dict for amounts >£1000 (I-27), else approves claim."""
        if approved_amount > _HITL_THRESHOLD:
            return {"status": "HITL_REQUIRED", "claim_id": claim_id}
        claim = self._claim_store.get(claim_id)
        if claim is None:
            raise ValueError(f"Claim not found: {claim_id}")
        if claim.status != ClaimStatus.UNDER_ASSESSMENT:
            raise ValueError(
                f"Claim {claim_id} must be UNDER_ASSESSMENT to approve, got {claim.status}"
            )
        updated = self._claim_store.update_status(claim_id, ClaimStatus.APPROVED, approved_amount)
        return {
            "claim_id": updated.claim_id,
            "status": updated.status.value,
            "approved_amount": str(updated.approved_amount),
        }

    def decline_claim(self, claim_id: str, reason: str) -> Claim:
        claim = self._claim_store.get(claim_id)
        if claim is None:
            raise ValueError(f"Claim not found: {claim_id}")
        if claim.status not in {ClaimStatus.UNDER_ASSESSMENT, ClaimStatus.FILED}:
            raise ValueError(
                f"Claim {claim_id} must be UNDER_ASSESSMENT or FILED to decline, got {claim.status}"
            )
        return self._claim_store.update_status(claim_id, ClaimStatus.DECLINED, None)

    def process_payout(self, claim_id: str) -> dict:
        claim = self._claim_store.get(claim_id)
        if claim is None:
            raise ValueError(f"Claim not found: {claim_id}")
        if claim.status != ClaimStatus.APPROVED:
            raise ValueError(
                f"Claim {claim_id} must be APPROVED to process payout, got {claim.status}"
            )
        self._claim_store.update_status(claim_id, ClaimStatus.PAID, claim.approved_amount)
        return {
            "status": "processed",
            "claim_id": claim_id,
            "amount": str(claim.approved_amount),
        }


__all__ = ["ClaimsProcessor"]
