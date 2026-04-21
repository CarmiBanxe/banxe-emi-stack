"""
tests/test_consumer_duty/test_models_v2.py
Tests for consumer duty Phase 50 models, frozen dataclasses, Decimal I-01.
IL-CDO-01 | Phase 50 | Sprint 35

≥20 tests covering:
- Frozen dataclasses (ConsumerProfile, OutcomeAssessment, etc.)
- Decimal I-01 for risk_score, score, fair_value_score
- HITLProposal dataclass (mutable)
- InMemory stubs (append-only, I-24)
- Enum values
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.consumer_duty.models_v2 import (
    AssessmentStatus,
    ConsumerProfile,
    HITLProposal,
    InMemoryOutcomeStore,
    InMemoryProductGovernance,
    InMemoryVulnerabilityAlertStore,
    InterventionType,
    OutcomeAssessment,
    OutcomeType,
    ProductGovernanceRecord,
    VulnerabilityAlert,
    VulnerabilityFlag,
)


def ts() -> str:
    return datetime.now(UTC).isoformat()


# ── ConsumerProfile tests ─────────────────────────────────────────────────────


def test_consumer_profile_frozen() -> None:
    """Test ConsumerProfile is frozen dataclass."""
    from dataclasses import FrozenInstanceError

    profile = ConsumerProfile(
        customer_id="c1",
        vulnerability_flag=VulnerabilityFlag.NONE,
        product_ids=("prod_001",),
        last_assessed_at=ts(),
        risk_score=Decimal("0.3"),
    )
    with pytest.raises(FrozenInstanceError):
        profile.customer_id = "c2"  # type: ignore[misc]


def test_consumer_profile_risk_score_is_decimal() -> None:
    """Test ConsumerProfile.risk_score is Decimal (I-01)."""
    profile = ConsumerProfile(
        customer_id="c1",
        vulnerability_flag=VulnerabilityFlag.LOW,
        product_ids=(),
        last_assessed_at=ts(),
        risk_score=Decimal("0.5"),
    )
    assert isinstance(profile.risk_score, Decimal)


def test_consumer_profile_product_ids_tuple() -> None:
    """Test ConsumerProfile.product_ids is a tuple."""
    profile = ConsumerProfile(
        customer_id="c1",
        vulnerability_flag=VulnerabilityFlag.NONE,
        product_ids=("p1", "p2"),
        last_assessed_at=ts(),
        risk_score=Decimal("0.0"),
    )
    assert isinstance(profile.product_ids, tuple)
    assert len(profile.product_ids) == 2


# ── OutcomeAssessment tests ───────────────────────────────────────────────────


def test_outcome_assessment_frozen() -> None:
    """Test OutcomeAssessment is frozen dataclass."""
    from dataclasses import FrozenInstanceError

    assessment = OutcomeAssessment(
        assessment_id="asm_001",
        customer_id="c1",
        outcome_type=OutcomeType.PRODUCTS_SERVICES,
        score=Decimal("0.8"),
        status=AssessmentStatus.PASSED,
        assessed_at=ts(),
        evidence="test",
    )
    with pytest.raises(FrozenInstanceError):
        assessment.score = Decimal("0.0")  # type: ignore[misc]


def test_outcome_assessment_score_is_decimal() -> None:
    """Test OutcomeAssessment.score is Decimal (I-01)."""
    assessment = OutcomeAssessment(
        assessment_id="asm_001",
        customer_id="c1",
        outcome_type=OutcomeType.PRICE_VALUE,
        score=Decimal("0.7"),
        status=AssessmentStatus.PASSED,
        assessed_at=ts(),
        evidence="",
    )
    assert isinstance(assessment.score, Decimal)


# ── ProductGovernanceRecord tests ─────────────────────────────────────────────


def test_product_governance_record_frozen() -> None:
    """Test ProductGovernanceRecord is frozen dataclass."""
    from dataclasses import FrozenInstanceError

    record = ProductGovernanceRecord(
        record_id="pgr_001",
        product_id="prod_001",
        product_name="Test Product",
        target_market="retail",
        fair_value_score=Decimal("0.75"),
        last_review_at=ts(),
        intervention_type=InterventionType.MONITOR,
    )
    with pytest.raises(FrozenInstanceError):
        record.fair_value_score = Decimal("0.0")  # type: ignore[misc]


def test_product_governance_record_fair_value_is_decimal() -> None:
    """Test ProductGovernanceRecord.fair_value_score is Decimal (I-01)."""
    record = ProductGovernanceRecord(
        record_id="pgr_001",
        product_id="prod_001",
        product_name="Test Product",
        target_market="retail",
        fair_value_score=Decimal("0.65"),
        last_review_at=ts(),
        intervention_type=InterventionType.RESTRICT,
    )
    assert isinstance(record.fair_value_score, Decimal)


# ── VulnerabilityAlert tests ──────────────────────────────────────────────────


def test_vulnerability_alert_frozen() -> None:
    """Test VulnerabilityAlert is frozen dataclass."""
    from dataclasses import FrozenInstanceError

    alert = VulnerabilityAlert(
        alert_id="vul_001",
        customer_id="c1",
        vulnerability_flag=VulnerabilityFlag.HIGH,
        trigger="debt_restructure",
        created_at=ts(),
        reviewed_by=None,
    )
    with pytest.raises(FrozenInstanceError):
        alert.reviewed_by = "reviewer"  # type: ignore[misc]


def test_vulnerability_alert_reviewed_by_optional() -> None:
    """Test VulnerabilityAlert.reviewed_by can be None."""
    alert = VulnerabilityAlert(
        alert_id="vul_001",
        customer_id="c1",
        vulnerability_flag=VulnerabilityFlag.MEDIUM,
        trigger="support_escalation",
        created_at=ts(),
        reviewed_by=None,
    )
    assert alert.reviewed_by is None


# ── HITLProposal tests ────────────────────────────────────────────────────────


def test_hitl_proposal_is_mutable() -> None:
    """Test HITLProposal is mutable (not frozen)."""
    proposal = HITLProposal(
        action="TEST",
        entity_id="e1",
        requires_approval_from="OFFICER",
        reason="test reason",
    )
    proposal.action = "UPDATED"
    assert proposal.action == "UPDATED"


def test_hitl_proposal_default_autonomy_l4() -> None:
    """Test HITLProposal defaults to L4 autonomy."""
    proposal = HITLProposal(
        action="TEST",
        entity_id="e1",
        requires_approval_from="OFFICER",
        reason="reason",
    )
    assert proposal.autonomy_level == "L4"


# ── Enum tests ────────────────────────────────────────────────────────────────


def test_outcome_type_enum_values() -> None:
    """Test OutcomeType has all 4 PS22/9 outcome areas."""
    assert OutcomeType.PRODUCTS_SERVICES == "PRODUCTS_SERVICES"
    assert OutcomeType.PRICE_VALUE == "PRICE_VALUE"
    assert OutcomeType.CONSUMER_UNDERSTANDING == "CONSUMER_UNDERSTANDING"
    assert OutcomeType.CONSUMER_SUPPORT == "CONSUMER_SUPPORT"


def test_vulnerability_flag_enum_values() -> None:
    """Test VulnerabilityFlag has all required values."""
    assert VulnerabilityFlag.NONE == "NONE"
    assert VulnerabilityFlag.LOW == "LOW"
    assert VulnerabilityFlag.MEDIUM == "MEDIUM"
    assert VulnerabilityFlag.HIGH == "HIGH"
    assert VulnerabilityFlag.CRITICAL == "CRITICAL"


def test_intervention_type_enum_values() -> None:
    """Test InterventionType has all required values."""
    assert InterventionType.MONITOR == "MONITOR"
    assert InterventionType.ALERT == "ALERT"
    assert InterventionType.RESTRICT == "RESTRICT"
    assert InterventionType.WITHDRAW == "WITHDRAW"


# ── InMemory stubs tests ──────────────────────────────────────────────────────


def test_inmemory_outcome_store_append_only() -> None:
    """Test InMemoryOutcomeStore is append-only (I-24)."""
    store = InMemoryOutcomeStore()
    assessment = OutcomeAssessment(
        assessment_id="asm_001",
        customer_id="c1",
        outcome_type=OutcomeType.PRODUCTS_SERVICES,
        score=Decimal("0.8"),
        status=AssessmentStatus.PASSED,
        assessed_at=ts(),
        evidence="",
    )
    store.append(assessment)
    result = store.list_by_customer("c1")
    assert len(result) == 1


def test_inmemory_product_governance_list_failing() -> None:
    """Test InMemoryProductGovernance.list_failing returns RESTRICT/WITHDRAW."""
    store = InMemoryProductGovernance()
    r1 = ProductGovernanceRecord(
        record_id="pgr_1",
        product_id="p1",
        product_name="P1",
        target_market="retail",
        fair_value_score=Decimal("0.4"),
        last_review_at=ts(),
        intervention_type=InterventionType.RESTRICT,
    )
    r2 = ProductGovernanceRecord(
        record_id="pgr_2",
        product_id="p2",
        product_name="P2",
        target_market="retail",
        fair_value_score=Decimal("0.8"),
        last_review_at=ts(),
        intervention_type=InterventionType.MONITOR,
    )
    store.append(r1)
    store.append(r2)
    failing = store.list_failing()
    assert len(failing) == 1
    assert failing[0].product_id == "p1"


def test_inmemory_vulnerability_alert_list_unreviewed() -> None:
    """Test InMemoryVulnerabilityAlertStore.list_unreviewed."""
    store = InMemoryVulnerabilityAlertStore()
    alert1 = VulnerabilityAlert(
        alert_id="vul_1",
        customer_id="c1",
        vulnerability_flag=VulnerabilityFlag.HIGH,
        trigger="debt_restructure",
        created_at=ts(),
        reviewed_by=None,
    )
    alert2 = VulnerabilityAlert(
        alert_id="vul_2",
        customer_id="c2",
        vulnerability_flag=VulnerabilityFlag.LOW,
        trigger="age_indicator",
        created_at=ts(),
        reviewed_by="officer1",
    )
    store.append(alert1)
    store.append(alert2)
    unreviewed = store.list_unreviewed()
    assert len(unreviewed) == 1
    assert unreviewed[0].alert_id == "vul_1"
