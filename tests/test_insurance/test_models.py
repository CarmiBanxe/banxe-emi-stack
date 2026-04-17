"""
tests/test_insurance/test_models.py
IL-INS-01 | Phase 26 — 18 tests for models, enums, protocols, InMemory stores.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.insurance.models import (
    Claim,
    ClaimStatus,
    CoverageType,
    InMemoryClaimStore,
    InMemoryInsuranceProductStore,
    InMemoryPolicyStore,
    InMemoryPremiumStore,
    InsuranceProduct,
    Policy,
    PolicyStatus,
    Premium,
    UnderwriterType,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def product() -> InsuranceProduct:
    return InsuranceProduct(
        product_id="ins-001",
        name="Travel Insurance",
        coverage_type=CoverageType.TRAVEL,
        base_premium=Decimal("4.99"),
        max_coverage=Decimal("10000.00"),
        underwriter=UnderwriterType.INTERNAL,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


@pytest.fixture
def policy() -> Policy:
    now = datetime(2026, 4, 17, tzinfo=UTC)
    return Policy(
        policy_id="pol-abc",
        customer_id="cust-001",
        product_id="ins-001",
        status=PolicyStatus.QUOTED,
        premium=Decimal("5.50"),
        coverage_amount=Decimal("1000.00"),
        start_date=now,
        end_date=now,
        policy_number="POL-ABCD1234",
        created_at=now,
    )


@pytest.fixture
def claim() -> Claim:
    return Claim(
        claim_id="clm-001",
        policy_id="pol-abc",
        customer_id="cust-001",
        status=ClaimStatus.FILED,
        claimed_amount=Decimal("250.00"),
        approved_amount=None,
        filed_at=datetime(2026, 4, 17, tzinfo=UTC),
        description="Lost luggage",
        evidence_urls=["https://example.com/photo.jpg"],
    )


# ── Enum tests ────────────────────────────────────────────────────────────────


def test_coverage_type_values() -> None:
    assert CoverageType.TRAVEL.value == "TRAVEL"
    assert CoverageType.PURCHASE.value == "PURCHASE"
    assert CoverageType.DEVICE.value == "DEVICE"
    assert CoverageType.PAYMENT_PROTECTION.value == "PAYMENT_PROTECTION"


def test_policy_status_values() -> None:
    assert PolicyStatus.QUOTED.value == "QUOTED"
    assert PolicyStatus.BOUND.value == "BOUND"
    assert PolicyStatus.ACTIVE.value == "ACTIVE"
    assert PolicyStatus.CANCELLED.value == "CANCELLED"


def test_claim_status_values() -> None:
    assert ClaimStatus.FILED.value == "FILED"
    assert ClaimStatus.APPROVED.value == "APPROVED"
    assert ClaimStatus.PAID.value == "PAID"


def test_underwriter_type_values() -> None:
    assert UnderwriterType.INTERNAL.value == "INTERNAL"
    assert UnderwriterType.LLOYDS_STUB.value == "LLOYDS_STUB"
    assert UnderwriterType.MUNICH_RE_STUB.value == "MUNICH_RE_STUB"


# ── Dataclass creation ────────────────────────────────────────────────────────


def test_insurance_product_creation(product: InsuranceProduct) -> None:
    assert product.product_id == "ins-001"
    assert isinstance(product.base_premium, Decimal)
    assert isinstance(product.max_coverage, Decimal)


def test_policy_creation(policy: Policy) -> None:
    assert policy.policy_id == "pol-abc"
    assert isinstance(policy.premium, Decimal)
    assert isinstance(policy.coverage_amount, Decimal)


def test_claim_creation(claim: Claim) -> None:
    assert claim.claim_id == "clm-001"
    assert isinstance(claim.claimed_amount, Decimal)
    assert claim.approved_amount is None
    assert isinstance(claim.evidence_urls, list)


def test_frozen_product_raises_on_mutation(product: InsuranceProduct) -> None:
    with pytest.raises((AttributeError, TypeError)):
        product.name = "changed"  # type: ignore[misc]


def test_frozen_policy_raises_on_mutation(policy: Policy) -> None:
    with pytest.raises((AttributeError, TypeError)):
        policy.status = PolicyStatus.ACTIVE  # type: ignore[misc]


# ── InMemory store CRUD ───────────────────────────────────────────────────────


def test_product_store_seeded() -> None:
    store = InMemoryInsuranceProductStore()
    products = store.list_products()
    assert len(products) == 4


def test_product_store_get_known() -> None:
    store = InMemoryInsuranceProductStore()
    p = store.get("ins-001")
    assert p is not None
    assert p.coverage_type == CoverageType.TRAVEL


def test_product_store_get_unknown_returns_none() -> None:
    store = InMemoryInsuranceProductStore()
    assert store.get("not-exist") is None


def test_product_store_filter_by_coverage_type() -> None:
    store = InMemoryInsuranceProductStore()
    results = store.list_by_coverage_type(CoverageType.DEVICE)
    assert len(results) == 1
    assert results[0].product_id == "ins-003"


def test_policy_store_save_and_get(policy: Policy) -> None:
    store = InMemoryPolicyStore()
    store.save(policy)
    retrieved = store.get(policy.policy_id)
    assert retrieved is not None
    assert retrieved.customer_id == "cust-001"


def test_claim_store_update_status(claim: Claim) -> None:
    store = InMemoryClaimStore()
    store.save(claim)
    updated = store.update_status(claim.claim_id, ClaimStatus.APPROVED, Decimal("200.00"))
    assert updated.status == ClaimStatus.APPROVED
    assert updated.approved_amount == Decimal("200.00")


def test_premium_store_list_by_policy() -> None:
    store = InMemoryPremiumStore()
    now = datetime(2026, 4, 17, tzinfo=UTC)
    p = Premium(
        premium_id="prem-001",
        policy_id="pol-abc",
        amount=Decimal("5.50"),
        due_date=now,
        paid_at=None,
        created_at=now,
    )
    store.save(p)
    results = store.list_by_policy("pol-abc")
    assert len(results) == 1
    assert results[0].amount == Decimal("5.50")
