"""
tests/test_insurance/test_underwriter_adapter.py
IL-INS-01 | Phase 26 — 10 tests for UnderwriterAdapter.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.insurance.models import (
    InMemoryInsuranceProductStore,
    Policy,
    PolicyStatus,
)
from services.insurance.underwriter_adapter import UnderwriterAdapter


@pytest.fixture
def store() -> InMemoryInsuranceProductStore:
    return InMemoryInsuranceProductStore()


@pytest.fixture
def adapter(store: InMemoryInsuranceProductStore) -> UnderwriterAdapter:
    return UnderwriterAdapter(product_store=store)


@pytest.fixture
def policy() -> Policy:
    now = datetime(2026, 4, 17, tzinfo=UTC)
    return Policy(
        policy_id="pol-001",
        customer_id="cust-001",
        product_id="ins-001",
        status=PolicyStatus.BOUND,
        premium=Decimal("5.50"),
        coverage_amount=Decimal("5000.00"),
        start_date=now,
        end_date=now,
        policy_number="POL-ABCDEF01",
        created_at=now,
    )


# ── submit_for_underwriting ───────────────────────────────────────────────────


def test_submit_returns_accepted(adapter: UnderwriterAdapter, policy: Policy) -> None:
    result = adapter.submit_for_underwriting(policy)
    assert result["status"] == "ACCEPTED"


def test_submit_reference_starts_with_uw(adapter: UnderwriterAdapter, policy: Policy) -> None:
    result = adapter.submit_for_underwriting(policy)
    assert result["reference"].startswith("UW-")


def test_submit_reference_format(adapter: UnderwriterAdapter, policy: Policy) -> None:
    result = adapter.submit_for_underwriting(policy)
    ref = result["reference"]
    assert len(ref) == 11  # "UW-" + 8 uppercase hex chars


def test_submit_returns_underwriter_internal(adapter: UnderwriterAdapter, policy: Policy) -> None:
    result = adapter.submit_for_underwriting(policy)
    assert result["underwriter"] == "INTERNAL"


def test_submit_lloyds_product(adapter: UnderwriterAdapter) -> None:
    now = datetime(2026, 4, 17, tzinfo=UTC)
    lloyds_policy = Policy(
        policy_id="pol-002",
        customer_id="cust-001",
        product_id="ins-003",
        status=PolicyStatus.BOUND,
        premium=Decimal("9.99"),
        coverage_amount=Decimal("1000.00"),
        start_date=now,
        end_date=now,
        policy_number="POL-ABCDEF02",
        created_at=now,
    )
    result = adapter.submit_for_underwriting(lloyds_policy)
    assert result["underwriter"] == "LLOYDS_STUB"


def test_submit_munich_re_product(adapter: UnderwriterAdapter) -> None:
    now = datetime(2026, 4, 17, tzinfo=UTC)
    munich_policy = Policy(
        policy_id="pol-003",
        customer_id="cust-001",
        product_id="ins-004",
        status=PolicyStatus.BOUND,
        premium=Decimal("14.99"),
        coverage_amount=Decimal("5000.00"),
        start_date=now,
        end_date=now,
        policy_number="POL-ABCDEF03",
        created_at=now,
    )
    result = adapter.submit_for_underwriting(munich_policy)
    assert result["underwriter"] == "MUNICH_RE_STUB"


def test_submit_generates_unique_references(adapter: UnderwriterAdapter, policy: Policy) -> None:
    ref1 = adapter.submit_for_underwriting(policy)["reference"]
    ref2 = adapter.submit_for_underwriting(policy)["reference"]
    assert ref1 != ref2


# ── check_underwriting_status ─────────────────────────────────────────────────


def test_check_status_returns_bound(adapter: UnderwriterAdapter) -> None:
    result = adapter.check_underwriting_status("UW-ABCD1234")
    assert result["status"] == "BOUND"


def test_check_status_echoes_reference(adapter: UnderwriterAdapter) -> None:
    ref = "UW-DEADBEEF"
    result = adapter.check_underwriting_status(ref)
    assert result["reference"] == ref


def test_check_status_any_reference(adapter: UnderwriterAdapter) -> None:
    result = adapter.check_underwriting_status("UW-FFFFFFFF")
    assert result["status"] == "BOUND"
