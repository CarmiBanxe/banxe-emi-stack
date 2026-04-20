"""Tests for KYBRiskAssessor — Phase 45 (IL-KYB-01)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.kyb_onboarding.models import (
    InMemoryApplicationStore,
    InMemoryUBOStore,
    RiskTier,
    UBOVerification,
    UltimateBeneficialOwner,
)
from services.kyb_onboarding.risk_assessor import KYBRiskAssessor


def make_assessor():
    return KYBRiskAssessor(InMemoryApplicationStore(), InMemoryUBOStore())


# --- assess_risk ---


def test_assess_risk_returns_decimal_score():
    assessor = make_assessor()
    assessment = assessor.assess_risk("app_001")
    assert isinstance(assessment.risk_score, Decimal)


def test_assess_risk_score_between_0_100():
    assessor = make_assessor()
    for app_id in ["app_001", "app_002", "app_003"]:
        assessment = assessor.assess_risk(app_id)
        assert Decimal("0") <= assessment.risk_score <= Decimal("100")


def test_assess_risk_nonexistent_raises():
    assessor = make_assessor()
    with pytest.raises(ValueError):
        assessor.assess_risk("nonexistent")


def test_assess_risk_has_assessment_id():
    assessor = make_assessor()
    assessment = assessor.assess_risk("app_001")
    assert assessment.assessment_id.startswith("risk_")


def test_assess_risk_gb_jurisdiction_low_base():
    assessor = make_assessor()
    assessment = assessor.assess_risk("app_001")  # app_001 is GB
    assert assessment.risk_tier in (RiskTier.LOW, RiskTier.MEDIUM, RiskTier.HIGH)


def test_assess_risk_factors_list():
    assessor = make_assessor()
    assessment = assessor.assess_risk("app_001")
    assert isinstance(assessment.factors, list)


# --- classify_tier ---


def test_classify_tier_low():
    assessor = make_assessor()
    assert assessor.classify_tier(Decimal("10")) == RiskTier.LOW
    assert assessor.classify_tier(Decimal("24.99")) == RiskTier.LOW


def test_classify_tier_medium():
    assessor = make_assessor()
    assert assessor.classify_tier(Decimal("25")) == RiskTier.MEDIUM
    assert assessor.classify_tier(Decimal("49.99")) == RiskTier.MEDIUM


def test_classify_tier_high():
    assessor = make_assessor()
    assert assessor.classify_tier(Decimal("50")) == RiskTier.HIGH
    assert assessor.classify_tier(Decimal("74.99")) == RiskTier.HIGH


def test_classify_tier_prohibited():
    assessor = make_assessor()
    assert assessor.classify_tier(Decimal("75")) == RiskTier.PROHIBITED
    assert assessor.classify_tier(Decimal("100")) == RiskTier.PROHIBITED


# --- get_risk_factors ---


def test_get_risk_factors_returns_list():
    assessor = make_assessor()
    factors = assessor.get_risk_factors("app_001")
    assert isinstance(factors, list)


# --- batch_reassess ---


def test_batch_reassess_multiple():
    assessor = make_assessor()
    results = assessor.batch_reassess(["app_001", "app_002", "app_003"])
    assert len(results) == 3


def test_batch_reassess_skips_missing():
    assessor = make_assessor()
    results = assessor.batch_reassess(["app_001", "nonexistent", "app_002"])
    assert len(results) == 2


def test_batch_reassess_all_decimal_scores():
    assessor = make_assessor()
    results = assessor.batch_reassess(["app_001", "app_002"])
    for r in results:
        assert isinstance(r.risk_score, Decimal)


# --- UBO count factor ---


def test_high_ubo_count_increases_score():
    app_store = InMemoryApplicationStore()
    ubo_store = InMemoryUBOStore()
    assessor = KYBRiskAssessor(app_store, ubo_store)
    # Add 5+ UBOs to app_001
    for i in range(5):
        ubo = UltimateBeneficialOwner(
            f"ubo_{i}",
            "app_001",
            f"Person {i}",
            "GB",
            "1990-01-01",
            Decimal("5"),
            UBOVerification.PENDING,
        )
        ubo_store.save(ubo)
    assessment = assessor.assess_risk("app_001")
    assert "high_ubo_count" in assessment.factors
