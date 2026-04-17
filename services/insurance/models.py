"""
services/insurance/models.py
IL-INS-01 | Phase 26

Domain models, enums, protocols, and InMemory stubs for insurance integration.
Amounts always Decimal (I-01). API layer uses strings (I-05).
HITL gate for claim payouts >£1000 (I-27).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol

# ── Enums ─────────────────────────────────────────────────────────────────────


class CoverageType(str, Enum):
    TRAVEL = "TRAVEL"
    PURCHASE = "PURCHASE"
    DEVICE = "DEVICE"
    PAYMENT_PROTECTION = "PAYMENT_PROTECTION"


class PolicyStatus(str, Enum):
    QUOTED = "QUOTED"
    BOUND = "BOUND"
    ACTIVE = "ACTIVE"
    LAPSED = "LAPSED"
    CANCELLED = "CANCELLED"
    CLAIMED = "CLAIMED"


class ClaimStatus(str, Enum):
    FILED = "FILED"
    UNDER_ASSESSMENT = "UNDER_ASSESSMENT"
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    PAID = "PAID"


class UnderwriterType(str, Enum):
    INTERNAL = "INTERNAL"
    LLOYDS_STUB = "LLOYDS_STUB"
    MUNICH_RE_STUB = "MUNICH_RE_STUB"


# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class InsuranceProduct:
    product_id: str
    name: str
    coverage_type: CoverageType
    base_premium: Decimal
    max_coverage: Decimal
    underwriter: UnderwriterType
    created_at: datetime


@dataclass(frozen=True)
class Policy:
    policy_id: str
    customer_id: str
    product_id: str
    status: PolicyStatus
    premium: Decimal
    coverage_amount: Decimal
    start_date: datetime
    end_date: datetime
    policy_number: str
    created_at: datetime


@dataclass(frozen=True)
class Claim:
    claim_id: str
    policy_id: str
    customer_id: str
    status: ClaimStatus
    claimed_amount: Decimal
    approved_amount: Decimal | None
    filed_at: datetime
    description: str
    evidence_urls: list[str]


@dataclass(frozen=True)
class Premium:
    premium_id: str
    policy_id: str
    amount: Decimal
    due_date: datetime
    paid_at: datetime | None
    created_at: datetime


@dataclass(frozen=True)
class RiskAssessment:
    assessment_id: str
    customer_id: str
    product_id: str
    risk_score: Decimal
    recommended_premium: Decimal
    assessed_at: datetime


# ── Protocols ─────────────────────────────────────────────────────────────────


class InsuranceProductStorePort(Protocol):
    def get(self, product_id: str) -> InsuranceProduct | None: ...
    def list_products(self) -> list[InsuranceProduct]: ...
    def list_by_coverage_type(self, ct: CoverageType) -> list[InsuranceProduct]: ...


class PolicyStorePort(Protocol):
    def save(self, p: Policy) -> None: ...
    def get(self, policy_id: str) -> Policy | None: ...
    def list_by_customer(self, customer_id: str) -> list[Policy]: ...


class ClaimStorePort(Protocol):
    def save(self, c: Claim) -> None: ...
    def get(self, claim_id: str) -> Claim | None: ...
    def list_by_policy(self, policy_id: str) -> list[Claim]: ...
    def update_status(
        self,
        claim_id: str,
        status: ClaimStatus,
        approved_amount: Decimal | None,
    ) -> Claim: ...


class PremiumStorePort(Protocol):
    def save(self, p: Premium) -> None: ...
    def list_by_policy(self, policy_id: str) -> list[Premium]: ...


# ── InMemory stubs ────────────────────────────────────────────────────────────

_SEED_PRODUCTS: list[InsuranceProduct] = [
    InsuranceProduct(
        product_id="ins-001",
        name="Travel Insurance",
        coverage_type=CoverageType.TRAVEL,
        base_premium=Decimal("4.99"),
        max_coverage=Decimal("10000.00"),
        underwriter=UnderwriterType.INTERNAL,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    ),
    InsuranceProduct(
        product_id="ins-002",
        name="Purchase Protection",
        coverage_type=CoverageType.PURCHASE,
        base_premium=Decimal("2.99"),
        max_coverage=Decimal("500.00"),
        underwriter=UnderwriterType.INTERNAL,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    ),
    InsuranceProduct(
        product_id="ins-003",
        name="Device Insurance",
        coverage_type=CoverageType.DEVICE,
        base_premium=Decimal("9.99"),
        max_coverage=Decimal("1500.00"),
        underwriter=UnderwriterType.LLOYDS_STUB,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    ),
    InsuranceProduct(
        product_id="ins-004",
        name="Payment Protection",
        coverage_type=CoverageType.PAYMENT_PROTECTION,
        base_premium=Decimal("14.99"),
        max_coverage=Decimal("5000.00"),
        underwriter=UnderwriterType.MUNICH_RE_STUB,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    ),
]


class InMemoryInsuranceProductStore:
    def __init__(self) -> None:
        self._products: dict[str, InsuranceProduct] = {p.product_id: p for p in _SEED_PRODUCTS}

    def get(self, product_id: str) -> InsuranceProduct | None:
        return self._products.get(product_id)

    def list_products(self) -> list[InsuranceProduct]:
        return list(self._products.values())

    def list_by_coverage_type(self, ct: CoverageType) -> list[InsuranceProduct]:
        return [p for p in self._products.values() if p.coverage_type == ct]


class InMemoryPolicyStore:
    def __init__(self) -> None:
        self._policies: dict[str, Policy] = {}

    def save(self, p: Policy) -> None:
        self._policies[p.policy_id] = p

    def get(self, policy_id: str) -> Policy | None:
        return self._policies.get(policy_id)

    def list_by_customer(self, customer_id: str) -> list[Policy]:
        return [p for p in self._policies.values() if p.customer_id == customer_id]


class InMemoryClaimStore:
    def __init__(self) -> None:
        self._claims: dict[str, Claim] = {}

    def save(self, c: Claim) -> None:
        self._claims[c.claim_id] = c

    def get(self, claim_id: str) -> Claim | None:
        return self._claims.get(claim_id)

    def list_by_policy(self, policy_id: str) -> list[Claim]:
        return [c for c in self._claims.values() if c.policy_id == policy_id]

    def update_status(
        self,
        claim_id: str,
        status: ClaimStatus,
        approved_amount: Decimal | None,
    ) -> Claim:
        claim = self._claims[claim_id]
        updated = Claim(
            claim_id=claim.claim_id,
            policy_id=claim.policy_id,
            customer_id=claim.customer_id,
            status=status,
            claimed_amount=claim.claimed_amount,
            approved_amount=approved_amount,
            filed_at=claim.filed_at,
            description=claim.description,
            evidence_urls=claim.evidence_urls,
        )
        self._claims[claim_id] = updated
        return updated


class InMemoryPremiumStore:
    def __init__(self) -> None:
        self._premiums: dict[str, Premium] = {}

    def save(self, p: Premium) -> None:
        self._premiums[p.premium_id] = p

    def list_by_policy(self, policy_id: str) -> list[Premium]:
        return [p for p in self._premiums.values() if p.policy_id == policy_id]


__all__ = [
    "CoverageType",
    "PolicyStatus",
    "ClaimStatus",
    "UnderwriterType",
    "InsuranceProduct",
    "Policy",
    "Claim",
    "Premium",
    "RiskAssessment",
    "InsuranceProductStorePort",
    "PolicyStorePort",
    "ClaimStorePort",
    "PremiumStorePort",
    "InMemoryInsuranceProductStore",
    "InMemoryPolicyStore",
    "InMemoryClaimStore",
    "InMemoryPremiumStore",
]
