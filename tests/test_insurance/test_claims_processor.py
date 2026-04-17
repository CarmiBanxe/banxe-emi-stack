"""
tests/test_insurance/test_claims_processor.py
IL-INS-01 | Phase 26 — 20 tests for ClaimsProcessor.
HITL gate for payouts >£1000 (I-27). All amounts Decimal (I-01).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.insurance.claims_processor import ClaimsProcessor
from services.insurance.models import (
    ClaimStatus,
    InMemoryClaimStore,
    InMemoryInsuranceProductStore,
    InMemoryPolicyStore,
    InMemoryPremiumStore,
)
from services.insurance.policy_manager import PolicyManager


@pytest.fixture
def stores() -> tuple:
    product_store = InMemoryInsuranceProductStore()
    policy_store = InMemoryPolicyStore()
    premium_store = InMemoryPremiumStore()
    claim_store = InMemoryClaimStore()
    return product_store, policy_store, premium_store, claim_store


@pytest.fixture
def active_policy_id(stores: tuple) -> str:
    product_store, policy_store, premium_store, claim_store = stores
    pm = PolicyManager(
        product_store=product_store,
        policy_store=policy_store,
        premium_store=premium_store,
        claim_store=claim_store,
    )
    p = pm.quote("cust-001", "ins-001", Decimal("5000.00"), 30)
    pm.bind(p.policy_id)
    pm.activate(p.policy_id)
    return p.policy_id


@pytest.fixture
def processor(stores: tuple) -> ClaimsProcessor:
    _, policy_store, _, claim_store = stores
    return ClaimsProcessor(policy_store=policy_store, claim_store=claim_store)


# ── file_claim ────────────────────────────────────────────────────────────────


def test_file_claim_on_active_policy(processor: ClaimsProcessor, active_policy_id: str) -> None:
    claim = processor.file_claim(
        active_policy_id, "cust-001", Decimal("200.00"), "Lost luggage", []
    )
    assert claim.status == ClaimStatus.FILED


def test_file_claim_amount_is_decimal(processor: ClaimsProcessor, active_policy_id: str) -> None:
    claim = processor.file_claim(active_policy_id, "cust-001", Decimal("200.00"), "Test", [])
    assert isinstance(claim.claimed_amount, Decimal)


def test_file_claim_non_active_policy_raises(stores: tuple) -> None:
    product_store, policy_store, premium_store, claim_store = stores
    pm = PolicyManager(
        product_store=product_store,
        policy_store=policy_store,
        premium_store=premium_store,
        claim_store=claim_store,
    )
    p = pm.quote("cust-001", "ins-001", Decimal("5000.00"), 30)
    processor = ClaimsProcessor(policy_store=policy_store, claim_store=claim_store)
    with pytest.raises(ValueError, match="not ACTIVE"):
        processor.file_claim(p.policy_id, "cust-001", Decimal("200.00"), "Test", [])


def test_file_claim_unknown_policy_raises(processor: ClaimsProcessor) -> None:
    with pytest.raises(ValueError):
        processor.file_claim("no-policy", "cust-001", Decimal("100.00"), "Test", [])


def test_file_claim_evidence_urls_stored(processor: ClaimsProcessor, active_policy_id: str) -> None:
    urls = ["https://example.com/a.jpg", "https://example.com/b.jpg"]
    claim = processor.file_claim(active_policy_id, "cust-001", Decimal("100.00"), "Damage", urls)
    assert claim.evidence_urls == urls


# ── assess_claim ──────────────────────────────────────────────────────────────


def test_assess_claim_transitions_to_under_assessment(
    processor: ClaimsProcessor, active_policy_id: str
) -> None:
    claim = processor.file_claim(active_policy_id, "cust-001", Decimal("200.00"), "Test", [])
    assessed = processor.assess_claim(claim.claim_id)
    assert assessed.status == ClaimStatus.UNDER_ASSESSMENT


def test_assess_claim_not_filed_raises(processor: ClaimsProcessor, active_policy_id: str) -> None:
    claim = processor.file_claim(active_policy_id, "cust-001", Decimal("200.00"), "Test", [])
    processor.assess_claim(claim.claim_id)
    with pytest.raises(ValueError):
        processor.assess_claim(claim.claim_id)


# ── approve_claim ─────────────────────────────────────────────────────────────


def test_approve_small_claim_returns_approved(
    processor: ClaimsProcessor, active_policy_id: str
) -> None:
    claim = processor.file_claim(active_policy_id, "cust-001", Decimal("500.00"), "Test", [])
    processor.assess_claim(claim.claim_id)
    result = processor.approve_claim(claim.claim_id, Decimal("500.00"), "agent")
    assert result["status"] == "APPROVED"


def test_approve_large_claim_returns_hitl(
    processor: ClaimsProcessor, active_policy_id: str
) -> None:
    claim = processor.file_claim(active_policy_id, "cust-001", Decimal("2000.00"), "Big claim", [])
    processor.assess_claim(claim.claim_id)
    result = processor.approve_claim(claim.claim_id, Decimal("1500.00"), "agent")
    assert result["status"] == "HITL_REQUIRED"
    assert result["claim_id"] == claim.claim_id


def test_approve_exactly_1000_is_not_hitl(
    processor: ClaimsProcessor, active_policy_id: str
) -> None:
    claim = processor.file_claim(active_policy_id, "cust-001", Decimal("1000.00"), "Test", [])
    processor.assess_claim(claim.claim_id)
    result = processor.approve_claim(claim.claim_id, Decimal("1000.00"), "agent")
    assert result["status"] == "APPROVED"


def test_approve_1001_is_hitl(processor: ClaimsProcessor, active_policy_id: str) -> None:
    claim = processor.file_claim(active_policy_id, "cust-001", Decimal("2000.00"), "Test", [])
    processor.assess_claim(claim.claim_id)
    result = processor.approve_claim(claim.claim_id, Decimal("1000.01"), "agent")
    assert result["status"] == "HITL_REQUIRED"


# ── decline_claim ─────────────────────────────────────────────────────────────


def test_decline_claim_from_under_assessment(
    processor: ClaimsProcessor, active_policy_id: str
) -> None:
    claim = processor.file_claim(active_policy_id, "cust-001", Decimal("200.00"), "Test", [])
    processor.assess_claim(claim.claim_id)
    declined = processor.decline_claim(claim.claim_id, "Insufficient evidence")
    assert declined.status == ClaimStatus.DECLINED


def test_decline_claim_from_filed(processor: ClaimsProcessor, active_policy_id: str) -> None:
    claim = processor.file_claim(active_policy_id, "cust-001", Decimal("200.00"), "Test", [])
    declined = processor.decline_claim(claim.claim_id, "Fraudulent")
    assert declined.status == ClaimStatus.DECLINED


# ── process_payout ────────────────────────────────────────────────────────────


def test_payout_approved_claim(processor: ClaimsProcessor, active_policy_id: str) -> None:
    claim = processor.file_claim(active_policy_id, "cust-001", Decimal("500.00"), "Test", [])
    processor.assess_claim(claim.claim_id)
    processor.approve_claim(claim.claim_id, Decimal("500.00"), "agent")
    result = processor.process_payout(claim.claim_id)
    assert result["status"] == "processed"
    assert result["amount"] == "500.00"


def test_payout_returns_claim_id(processor: ClaimsProcessor, active_policy_id: str) -> None:
    claim = processor.file_claim(active_policy_id, "cust-001", Decimal("300.00"), "Test", [])
    processor.assess_claim(claim.claim_id)
    processor.approve_claim(claim.claim_id, Decimal("300.00"), "agent")
    result = processor.process_payout(claim.claim_id)
    assert result["claim_id"] == claim.claim_id


def test_payout_non_approved_raises(processor: ClaimsProcessor, active_policy_id: str) -> None:
    claim = processor.file_claim(active_policy_id, "cust-001", Decimal("200.00"), "Test", [])
    processor.assess_claim(claim.claim_id)
    with pytest.raises(ValueError, match="APPROVED"):
        processor.process_payout(claim.claim_id)
