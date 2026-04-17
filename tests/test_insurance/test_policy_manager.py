"""
tests/test_insurance/test_policy_manager.py
IL-INS-01 | Phase 26 — 20 tests for PolicyManager.
"""

from __future__ import annotations

from decimal import Decimal
import re

import pytest

from services.insurance.models import (
    InMemoryClaimStore,
    InMemoryInsuranceProductStore,
    InMemoryPolicyStore,
    InMemoryPremiumStore,
    PolicyStatus,
)
from services.insurance.policy_manager import PolicyManager


@pytest.fixture
def manager() -> PolicyManager:
    return PolicyManager(
        product_store=InMemoryInsuranceProductStore(),
        policy_store=InMemoryPolicyStore(),
        premium_store=InMemoryPremiumStore(),
        claim_store=InMemoryClaimStore(),
    )


@pytest.fixture
def quoted_policy_id(manager: PolicyManager) -> str:
    policy = manager.quote("cust-001", "ins-001", Decimal("5000.00"), 30)
    return policy.policy_id


@pytest.fixture
def bound_policy_id(manager: PolicyManager, quoted_policy_id: str) -> str:
    manager.bind(quoted_policy_id)
    return quoted_policy_id


@pytest.fixture
def active_policy_id(manager: PolicyManager, bound_policy_id: str) -> str:
    manager.activate(bound_policy_id)
    return bound_policy_id


# ── quote ─────────────────────────────────────────────────────────────────────


def test_quote_creates_quoted_status(manager: PolicyManager) -> None:
    policy = manager.quote("cust-001", "ins-001", Decimal("5000.00"), 30)
    assert policy.status == PolicyStatus.QUOTED


def test_quote_premium_is_decimal(manager: PolicyManager) -> None:
    policy = manager.quote("cust-001", "ins-001", Decimal("5000.00"), 30)
    assert isinstance(policy.premium, Decimal)


def test_quote_coverage_amount_stored(manager: PolicyManager) -> None:
    policy = manager.quote("cust-001", "ins-001", Decimal("3000.00"), 30)
    assert policy.coverage_amount == Decimal("3000.00")


def test_quote_policy_number_format(manager: PolicyManager) -> None:
    policy = manager.quote("cust-001", "ins-001", Decimal("5000.00"), 30)
    assert re.match(r"POL-[A-F0-9]{8}$", policy.policy_number)


def test_quote_unknown_product_raises(manager: PolicyManager) -> None:
    with pytest.raises(ValueError, match="not found"):
        manager.quote("cust-001", "no-product", Decimal("1000.00"), 30)


def test_quote_stores_policy(manager: PolicyManager) -> None:
    policy = manager.quote("cust-001", "ins-001", Decimal("5000.00"), 30)
    retrieved = manager.get_policy(policy.policy_id)
    assert retrieved is not None


# ── bind ──────────────────────────────────────────────────────────────────────


def test_bind_transitions_to_bound(manager: PolicyManager, quoted_policy_id: str) -> None:
    policy = manager.bind(quoted_policy_id)
    assert policy.status == PolicyStatus.BOUND


def test_bind_creates_premium_record(manager: PolicyManager) -> None:
    policy = manager.quote("cust-001", "ins-001", Decimal("5000.00"), 30)
    manager.bind(policy.policy_id)
    premiums = manager._premium_store.list_by_policy(policy.policy_id)
    assert len(premiums) == 1


def test_bind_premium_amount_matches_policy(manager: PolicyManager) -> None:
    policy = manager.quote("cust-001", "ins-001", Decimal("5000.00"), 30)
    manager.bind(policy.policy_id)
    premiums = manager._premium_store.list_by_policy(policy.policy_id)
    assert premiums[0].amount == policy.premium


def test_bind_already_bound_raises(manager: PolicyManager, bound_policy_id: str) -> None:
    with pytest.raises(ValueError):
        manager.bind(bound_policy_id)


# ── activate ──────────────────────────────────────────────────────────────────


def test_activate_transitions_to_active(manager: PolicyManager, bound_policy_id: str) -> None:
    policy = manager.activate(bound_policy_id)
    assert policy.status == PolicyStatus.ACTIVE


def test_activate_from_quoted_raises(manager: PolicyManager, quoted_policy_id: str) -> None:
    with pytest.raises(ValueError):
        manager.activate(quoted_policy_id)


# ── cancel ────────────────────────────────────────────────────────────────────


def test_cancel_active_policy(manager: PolicyManager, active_policy_id: str) -> None:
    policy = manager.cancel(active_policy_id)
    assert policy.status == PolicyStatus.CANCELLED


def test_cancel_quoted_policy(manager: PolicyManager, quoted_policy_id: str) -> None:
    policy = manager.cancel(quoted_policy_id)
    assert policy.status == PolicyStatus.CANCELLED


def test_cancel_bound_policy(manager: PolicyManager, bound_policy_id: str) -> None:
    policy = manager.cancel(bound_policy_id)
    assert policy.status == PolicyStatus.CANCELLED


def test_cancel_already_cancelled_raises(manager: PolicyManager, active_policy_id: str) -> None:
    manager.cancel(active_policy_id)
    with pytest.raises(ValueError):
        manager.cancel(active_policy_id)


# ── get_policy / list_policies ────────────────────────────────────────────────


def test_get_policy_not_found_returns_none(manager: PolicyManager) -> None:
    assert manager.get_policy("no-such-id") is None


def test_list_policies_by_customer(manager: PolicyManager) -> None:
    manager.quote("cust-A", "ins-001", Decimal("1000.00"), 30)
    manager.quote("cust-A", "ins-002", Decimal("500.00"), 30)
    manager.quote("cust-B", "ins-001", Decimal("1000.00"), 30)
    policies = manager.list_policies("cust-A")
    assert len(policies) == 2
    assert all(p.customer_id == "cust-A" for p in policies)
