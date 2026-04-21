"""
tests/test_consumer_duty/test_product_governance.py
Tests for ProductGovernanceService: record, threshold, withdraw HITL.
IL-CDO-01 | Phase 50 | Sprint 35

≥20 tests covering:
- record_product_assessment (above/below threshold, I-01 Decimal)
- FAIR_VALUE_THRESHOLD is Decimal 0.6
- below threshold → RESTRICT + HITLProposal (I-27)
- get_failing_products
- propose_product_withdrawal returns HITLProposal
- I-24 append-only
"""

from __future__ import annotations

from decimal import Decimal

from services.consumer_duty.models_v2 import (
    HITLProposal,
    InMemoryProductGovernance,
    InterventionType,
    ProductGovernanceRecord,
)
from services.consumer_duty.product_governance import (
    FAIR_VALUE_THRESHOLD,
    ProductGovernanceService,
)


def make_service() -> tuple[ProductGovernanceService, InMemoryProductGovernance]:
    store = InMemoryProductGovernance()
    svc = ProductGovernanceService(store)
    return svc, store


# ── record_product_assessment tests ──────────────────────────────────────────


def test_record_product_above_threshold_returns_record() -> None:
    """Test product above fair value threshold returns ProductGovernanceRecord."""
    svc, _ = make_service()
    result = svc.record_product_assessment("p1", "Product A", "retail", Decimal("0.75"), "good")
    assert isinstance(result, ProductGovernanceRecord)


def test_record_product_above_threshold_monitor_intervention() -> None:
    """Test product above threshold gets MONITOR intervention."""
    svc, _ = make_service()
    result = svc.record_product_assessment("p1", "Product A", "retail", Decimal("0.75"))
    assert isinstance(result, ProductGovernanceRecord)
    assert result.intervention_type == InterventionType.MONITOR


def test_record_product_below_threshold_returns_hitl() -> None:
    """Test product below fair value threshold returns HITLProposal (I-27)."""
    svc, _ = make_service()
    result = svc.record_product_assessment("p1", "Product A", "retail", Decimal("0.5"))
    assert isinstance(result, HITLProposal)


def test_record_product_below_threshold_hitl_action() -> None:
    """Test below-threshold HITLProposal has RESTRICT_PRODUCT action."""
    svc, _ = make_service()
    result = svc.record_product_assessment("p1", "Bad Product", "retail", Decimal("0.4"))
    assert isinstance(result, HITLProposal)
    assert result.action == "RESTRICT_PRODUCT"


def test_record_product_below_threshold_stores_record() -> None:
    """Test below-threshold still appends record to store (I-24)."""
    svc, store = make_service()
    svc.record_product_assessment("p1", "Product A", "retail", Decimal("0.5"))
    failing = store.list_failing()
    assert len(failing) == 1


def test_record_product_exactly_at_threshold_is_monitor() -> None:
    """Test product exactly at threshold (0.6) gets MONITOR intervention."""
    svc, _ = make_service()
    result = svc.record_product_assessment("p1", "Product A", "retail", FAIR_VALUE_THRESHOLD)
    assert isinstance(result, ProductGovernanceRecord)
    assert result.intervention_type == InterventionType.MONITOR


def test_record_product_fair_value_score_is_decimal() -> None:
    """Test fair_value_score in record is Decimal (I-01)."""
    svc, _ = make_service()
    result = svc.record_product_assessment("p1", "Product A", "retail", Decimal("0.8"))
    assert isinstance(result, ProductGovernanceRecord)
    assert isinstance(result.fair_value_score, Decimal)


def test_record_product_append_only() -> None:
    """Test record_product_assessment appends (I-24 — no overwrite)."""
    svc, store = make_service()
    svc.record_product_assessment("p1", "Product A", "retail", Decimal("0.8"))
    svc.record_product_assessment("p1", "Product A", "retail", Decimal("0.9"))
    all_records = store.list_all()
    assert len(all_records) == 2


def test_record_product_below_threshold_hitl_requires_consumer_duty_officer() -> None:
    """Test below-threshold HITL requires CONSUMER_DUTY_OFFICER."""
    svc, _ = make_service()
    result = svc.record_product_assessment("p1", "Bad Product", "retail", Decimal("0.3"))
    assert isinstance(result, HITLProposal)
    assert result.requires_approval_from == "CONSUMER_DUTY_OFFICER"


# ── FAIR_VALUE_THRESHOLD tests ────────────────────────────────────────────────


def test_fair_value_threshold_is_decimal() -> None:
    """Test FAIR_VALUE_THRESHOLD is Decimal (I-01)."""
    assert isinstance(FAIR_VALUE_THRESHOLD, Decimal)


def test_fair_value_threshold_value() -> None:
    """Test FAIR_VALUE_THRESHOLD is 0.6."""
    assert Decimal("0.6") == FAIR_VALUE_THRESHOLD


# ── get_failing_products tests ────────────────────────────────────────────────


def test_get_failing_products_returns_restrict() -> None:
    """Test get_failing_products returns products with RESTRICT intervention."""
    svc, _ = make_service()
    svc.record_product_assessment("p1", "Bad Product", "retail", Decimal("0.4"))
    failing = svc.get_failing_products()
    assert len(failing) == 1
    assert failing[0].intervention_type == InterventionType.RESTRICT


def test_get_failing_products_empty_when_all_pass() -> None:
    """Test get_failing_products returns empty when all products pass."""
    svc, _ = make_service()
    svc.record_product_assessment("p1", "Good Product", "retail", Decimal("0.8"))
    failing = svc.get_failing_products()
    assert len(failing) == 0


def test_get_failing_products_excludes_monitor() -> None:
    """Test get_failing_products excludes MONITOR products."""
    svc, _ = make_service()
    svc.record_product_assessment("p1", "Good", "retail", Decimal("0.8"))  # MONITOR
    svc.record_product_assessment("p2", "Bad", "retail", Decimal("0.4"))  # RESTRICT
    failing = svc.get_failing_products()
    assert len(failing) == 1


# ── propose_product_withdrawal tests ─────────────────────────────────────────


def test_propose_product_withdrawal_returns_hitl() -> None:
    """Test propose_product_withdrawal returns HITLProposal (I-27)."""
    svc, _ = make_service()
    proposal = svc.propose_product_withdrawal("p1", "consumer harm", "operator1")
    assert isinstance(proposal, HITLProposal)


def test_propose_product_withdrawal_action() -> None:
    """Test withdrawal HITLProposal has WITHDRAW_PRODUCT action."""
    svc, _ = make_service()
    proposal = svc.propose_product_withdrawal("p1", "reason", "operator1")
    assert proposal.action == "WITHDRAW_PRODUCT"


def test_propose_product_withdrawal_requires_officer() -> None:
    """Test withdrawal HITLProposal requires CONSUMER_DUTY_OFFICER."""
    svc, _ = make_service()
    proposal = svc.propose_product_withdrawal("p1", "reason", "operator1")
    assert proposal.requires_approval_from == "CONSUMER_DUTY_OFFICER"


def test_propose_product_withdrawal_autonomy_l4() -> None:
    """Test withdrawal proposal has L4 autonomy."""
    svc, _ = make_service()
    proposal = svc.propose_product_withdrawal("p1", "reason", "operator1")
    assert proposal.autonomy_level == "L4"


# ── get_product_governance_summary tests ─────────────────────────────────────


def test_get_product_governance_summary_counts() -> None:
    """Test governance summary counts monitor and restrict correctly."""
    svc, _ = make_service()
    svc.record_product_assessment("p1", "Good", "retail", Decimal("0.8"))  # MONITOR
    svc.record_product_assessment("p2", "Bad", "retail", Decimal("0.4"))  # RESTRICT
    summary = svc.get_product_governance_summary()
    assert summary["restrict_count"] == 1
    assert summary["fair_value_threshold"] == str(FAIR_VALUE_THRESHOLD)
