"""
services/insurance/policy_manager.py
IL-INS-01 | Phase 26

Policy lifecycle management: QUOTED → BOUND → ACTIVE → CANCELLED/LAPSED.
State transitions enforced with ValueError (I-24).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import uuid

from services.insurance.models import (
    ClaimStorePort,
    InMemoryClaimStore,
    InMemoryInsuranceProductStore,
    InMemoryPolicyStore,
    InMemoryPremiumStore,
    InsuranceProductStorePort,
    Policy,
    PolicyStatus,
    PolicyStorePort,
    Premium,
    PremiumStorePort,
)
from services.insurance.premium_calculator import PremiumCalculator

_VALID_TRANSITIONS: dict[PolicyStatus, set[PolicyStatus]] = {
    PolicyStatus.QUOTED: {PolicyStatus.BOUND, PolicyStatus.CANCELLED},
    PolicyStatus.BOUND: {PolicyStatus.ACTIVE, PolicyStatus.CANCELLED},
    PolicyStatus.ACTIVE: {PolicyStatus.CANCELLED, PolicyStatus.LAPSED, PolicyStatus.CLAIMED},
    PolicyStatus.LAPSED: set(),
    PolicyStatus.CANCELLED: set(),
    PolicyStatus.CLAIMED: set(),
}


class PolicyManager:
    def __init__(
        self,
        product_store: InsuranceProductStorePort | None = None,
        policy_store: PolicyStorePort | None = None,
        premium_store: PremiumStorePort | None = None,
        claim_store: ClaimStorePort | None = None,
    ) -> None:
        self._product_store: InsuranceProductStorePort = (
            product_store or InMemoryInsuranceProductStore()
        )
        self._policy_store: PolicyStorePort = policy_store or InMemoryPolicyStore()
        self._premium_store: PremiumStorePort = premium_store or InMemoryPremiumStore()
        # claim_store kept for future use — not used by policy transitions directly
        self._claim_store: ClaimStorePort = claim_store or InMemoryClaimStore()
        self._calculator = PremiumCalculator(self._product_store)

    def quote(
        self,
        customer_id: str,
        product_id: str,
        coverage_amount: Decimal,
        term_days: int,
    ) -> Policy:
        product = self._product_store.get(product_id)
        if product is None:
            raise ValueError(f"Product not found: {product_id}")
        risk_assessment = self._calculator.assess_risk(customer_id, product_id, coverage_amount)
        premium = self._calculator.calculate(
            product, coverage_amount, term_days, risk_assessment.risk_score
        )
        now = datetime.now(UTC)
        policy = Policy(
            policy_id=str(uuid.uuid4()),
            customer_id=customer_id,
            product_id=product_id,
            status=PolicyStatus.QUOTED,
            premium=premium,
            coverage_amount=coverage_amount,
            start_date=now,
            end_date=now + timedelta(days=term_days),
            policy_number=f"POL-{uuid.uuid4().hex[:8].upper()}",
            created_at=now,
        )
        self._policy_store.save(policy)
        return policy

    def _transition(self, policy_id: str, target: PolicyStatus) -> Policy:
        policy = self._policy_store.get(policy_id)
        if policy is None:
            raise ValueError(f"Policy not found: {policy_id}")
        allowed = _VALID_TRANSITIONS.get(policy.status, set())
        if target not in allowed:
            raise ValueError(
                f"Invalid transition {policy.status} → {target} for policy {policy_id}"
            )
        updated = replace(policy, status=target)
        self._policy_store.save(updated)
        return updated

    def bind(self, policy_id: str) -> Policy:
        policy = self._transition(policy_id, PolicyStatus.BOUND)
        premium_record = Premium(
            premium_id=str(uuid.uuid4()),
            policy_id=policy_id,
            amount=policy.premium,
            due_date=policy.start_date,
            paid_at=None,
            created_at=datetime.now(UTC),
        )
        self._premium_store.save(premium_record)
        return policy

    def activate(self, policy_id: str) -> Policy:
        return self._transition(policy_id, PolicyStatus.ACTIVE)

    def cancel(self, policy_id: str) -> Policy:
        return self._transition(policy_id, PolicyStatus.CANCELLED)

    def get_policy(self, policy_id: str) -> Policy | None:
        return self._policy_store.get(policy_id)

    def list_policies(self, customer_id: str) -> list[Policy]:
        return self._policy_store.list_by_customer(customer_id)


__all__ = ["PolicyManager"]
