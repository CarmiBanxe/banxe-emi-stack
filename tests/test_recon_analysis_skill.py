"""Tests for ReconAnalysisSkill — discrepancy classification."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from agents.compliance.skills.recon_analysis import (
    AnalysisReport,
    DiscrepancyClass,
    ReconAnalysisSkill,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_result(account_id: str, status: str, discrepancy: str) -> MagicMock:
    """Create a mock ReconResult."""
    result = MagicMock()
    result.account_id = account_id
    result.status = status
    result.discrepancy = Decimal(discrepancy)
    result.account_type = "client_funds"
    result.currency = "GBP"
    return result


# ── Test: FRAUD_RISK for discrepancy > £50k ──────────────────────────────────


def test_fraud_risk_classification_above_50k():
    """Discrepancy > £50,000 is classified as FRAUD_RISK with confidence 0.95."""
    skill = ReconAnalysisSkill()
    result = make_result("acct-001", "DISCREPANCY", "75000.00")

    reports = skill.analyze([result])

    assert len(reports) == 1
    assert reports[0].classification == DiscrepancyClass.FRAUD_RISK
    assert reports[0].confidence == Decimal("0.95")
    assert isinstance(reports[0].confidence, Decimal)  # NEVER float


def test_fraud_risk_at_exactly_50001():
    """Discrepancy of £50,001 triggers FRAUD_RISK."""
    skill = ReconAnalysisSkill()
    result = make_result("acct-002", "DISCREPANCY", "50001.00")
    reports = skill.analyze([result])
    assert reports[0].classification == DiscrepancyClass.FRAUD_RISK


def test_fraud_risk_recommendation_contains_mlro():
    """FRAUD_RISK recommendation mentions MLRO escalation."""
    skill = ReconAnalysisSkill()
    result = make_result("acct-003", "DISCREPANCY", "100000.00")
    reports = skill.analyze([result])
    assert "MLRO" in reports[0].recommendation


# ── Test: TIMING_DIFFERENCE for small discrepancy ────────────────────────────


def test_timing_difference_below_100():
    """Discrepancy < £100 is classified as TIMING_DIFFERENCE with confidence 0.80."""
    skill = ReconAnalysisSkill()
    result = make_result("acct-004", "DISCREPANCY", "50.00")

    reports = skill.analyze([result])

    assert reports[0].classification == DiscrepancyClass.TIMING_DIFFERENCE
    assert reports[0].confidence == Decimal("0.80")
    assert isinstance(reports[0].confidence, Decimal)


def test_timing_difference_at_99_99():
    """Discrepancy of £99.99 (just below threshold) = TIMING_DIFFERENCE."""
    skill = ReconAnalysisSkill()
    result = make_result("acct-005", "DISCREPANCY", "99.99")
    reports = skill.analyze([result])
    assert reports[0].classification == DiscrepancyClass.TIMING_DIFFERENCE


# ── Test: SYSTEMATIC_ERROR for recurring discrepancy ─────────────────────────


def test_systematic_error_when_2_consecutive_discrepancy_days():
    """Account with 2+ consecutive DISCREPANCY days in history = SYSTEMATIC_ERROR."""
    history = {
        "acct-006": [
            {"date": "2026-04-08", "discrepancy": Decimal("500.00"), "status": "DISCREPANCY"},
            {"date": "2026-04-09", "discrepancy": Decimal("500.00"), "status": "DISCREPANCY"},
        ]
    }
    skill = ReconAnalysisSkill(history=history)
    result = make_result("acct-006", "DISCREPANCY", "500.00")

    reports = skill.analyze([result])

    assert reports[0].classification == DiscrepancyClass.SYSTEMATIC_ERROR
    assert reports[0].confidence == Decimal("0.90")


# ── Test: MATCHED classification ─────────────────────────────────────────────


def test_matched_classification():
    """MATCHED status = MATCHED classification with confidence 1.00."""
    skill = ReconAnalysisSkill()
    result = make_result("acct-007", "MATCHED", "0.00")

    reports = skill.analyze([result])

    assert reports[0].classification == DiscrepancyClass.MATCHED
    assert reports[0].confidence == Decimal("1.00")


# ── Test: MISSING_TRANSACTION default ────────────────────────────────────────


def test_missing_transaction_default():
    """Discrepancy between £100-£50000 with no history = MISSING_TRANSACTION."""
    skill = ReconAnalysisSkill()
    result = make_result("acct-008", "DISCREPANCY", "5000.00")

    reports = skill.analyze([result])

    assert reports[0].classification == DiscrepancyClass.MISSING_TRANSACTION
    assert reports[0].confidence == Decimal("0.75")


# ── Test: AnalysisReport is frozen dataclass with Decimal confidence ──────────


def test_analysis_report_is_frozen_dataclass():
    """AnalysisReport is a frozen dataclass — cannot be mutated."""
    report = AnalysisReport(
        account_id="test-account",
        classification=DiscrepancyClass.MATCHED,
        confidence=Decimal("1.00"),
        recommendation="No action",
        pattern_detected="none",
    )

    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        report.confidence = Decimal("0.50")  # type: ignore[misc]


def test_analysis_report_confidence_is_decimal():
    """AnalysisReport.confidence is always Decimal — never float."""
    skill = ReconAnalysisSkill()
    result = make_result("acct-009", "MATCHED", "0.00")
    reports = skill.analyze([result])

    assert isinstance(reports[0].confidence, Decimal)
    assert not isinstance(reports[0].confidence, float)


# ── Test: multiple results analyzed ──────────────────────────────────────────


def test_analyze_multiple_results():
    """analyze() handles a list of mixed results correctly."""
    skill = ReconAnalysisSkill()
    results = [
        make_result("acct-010", "MATCHED", "0.00"),
        make_result("acct-011", "DISCREPANCY", "75000.00"),  # FRAUD_RISK
        make_result("acct-012", "DISCREPANCY", "50.00"),  # TIMING
    ]

    reports = skill.analyze(results)

    assert len(reports) == 3
    assert reports[0].classification == DiscrepancyClass.MATCHED
    assert reports[1].classification == DiscrepancyClass.FRAUD_RISK
    assert reports[2].classification == DiscrepancyClass.TIMING_DIFFERENCE
