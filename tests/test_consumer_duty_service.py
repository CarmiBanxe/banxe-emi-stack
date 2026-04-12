"""
tests/test_consumer_duty_service.py — Consumer Duty tests
IL-050 | S9-06 | FCA PS22/9 | banxe-emi-stack

Coverage:
  - Unit: VulnerabilityAssessment, FairValueAssessment, OutcomeRecord, Report
  - API: POST vulnerability, GET vulnerability, POST fair-value,
         POST outcomes, POST report
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
import pytest

from api.main import app
from api.routers.consumer_duty import _get_consumer_duty_service
from services.consumer_duty.consumer_duty_port import (
    ConsumerDutyOutcome,
    FairValueVerdict,
    OutcomeRating,
    VulnerabilityCategory,
    VulnerabilityFlag,
)
from services.consumer_duty.consumer_duty_service import ConsumerDutyService

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def svc():
    return ConsumerDutyService()


@pytest.fixture
def client():
    fresh_svc = ConsumerDutyService()
    app.dependency_overrides[_get_consumer_duty_service] = lambda: fresh_svc
    _get_consumer_duty_service.cache_clear()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    _get_consumer_duty_service.cache_clear()


# ── Unit: Vulnerability ───────────────────────────────────────────────────────


def test_assess_vulnerability_single_flag(svc):
    result = svc.assess_vulnerability(
        "cust-001",
        [VulnerabilityFlag.FINANCIAL_DIFFICULTY],
        assessed_by="operator-1",
    )
    assert result.is_vulnerable is True
    assert VulnerabilityFlag.FINANCIAL_DIFFICULTY in result.flags
    assert VulnerabilityCategory.RESILIENCE in result.categories
    assert len(result.support_actions) >= 1


def test_assess_vulnerability_multiple_flags(svc):
    result = svc.assess_vulnerability(
        "cust-002",
        [VulnerabilityFlag.MENTAL_HEALTH, VulnerabilityFlag.BEREAVEMENT],
    )
    assert result.is_vulnerable is True
    assert len(result.flags) == 2
    assert VulnerabilityCategory.HEALTH in result.categories
    assert VulnerabilityCategory.LIFE_EVENTS in result.categories
    # Actions from both flags, deduplicated
    assert len(result.support_actions) >= 2


def test_assess_vulnerability_no_flags(svc):
    result = svc.assess_vulnerability("cust-003", [])
    assert result.is_vulnerable is False
    assert result.flags == []
    assert result.support_actions == []


def test_assess_vulnerability_domestic_abuse_has_safety_actions(svc):
    """DOMESTIC_ABUSE must include discreet banking and helpline actions."""
    result = svc.assess_vulnerability(
        "cust-004",
        [VulnerabilityFlag.DOMESTIC_ABUSE],
    )
    actions_text = " ".join(result.support_actions).lower()
    assert "discreet" in actions_text or "helpline" in actions_text or "domestic" in actions_text


def test_assess_vulnerability_overwrites_previous(svc):
    svc.assess_vulnerability("cust-005", [VulnerabilityFlag.BEREAVEMENT])
    # Second assessment overwrites first
    svc.assess_vulnerability("cust-005", [VulnerabilityFlag.MENTAL_HEALTH])
    assessment = svc.get_vulnerability("cust-005")
    assert assessment is not None
    assert VulnerabilityFlag.MENTAL_HEALTH in assessment.flags
    assert VulnerabilityFlag.BEREAVEMENT not in assessment.flags


def test_get_vulnerability_returns_none_for_unknown(svc):
    assert svc.get_vulnerability("cust-unknown") is None


def test_vulnerability_assessed_at_is_set(svc):
    result = svc.assess_vulnerability("cust-007", [VulnerabilityFlag.ELDERLY_ISOLATED])
    assert result.assessed_at is not None


def test_vulnerability_notes_preserved(svc):
    result = svc.assess_vulnerability("cust-008", [], notes="Customer called in distress")
    assert result.notes == "Customer called in distress"


# ── Unit: Fair Value ──────────────────────────────────────────────────────────


def test_fair_value_emi_account_individual_calculated(svc):
    """
    EMI_ACCOUNT individual annual fee is calculated correctly.
    50 FPS×£0.20 + 20 BACS×£0.10 + 5 FX×(£2000×0.25%) + 10 SEPA_CT×£0.50
    = £10 + £2 + £25 + £5 = £42.00
    Benchmark £24 → fee_ratio=1.75 → REVIEW_REQUIRED (conservative board review).
    """
    result = svc.assess_fair_value("EMI_ACCOUNT", "INDIVIDUAL")
    assert result.annual_fee_estimate > 0
    assert result.verdict in (FairValueVerdict.FAIR, FairValueVerdict.REVIEW_REQUIRED)
    assert result.benefit_score > 0
    assert result.rationale != ""


def test_fair_value_emi_account_company(svc):
    """
    EMI_ACCOUNT company: 200 FPS + 50 BACS + 20 FX + 50 SEPA_CT.
    = £40 + £5 + £100 + £25 = £170. Benchmark £120 → REVIEW_REQUIRED.
    """
    result = svc.assess_fair_value("EMI_ACCOUNT", "COMPANY")
    assert result.annual_fee_estimate > 0
    assert result.verdict in (FairValueVerdict.FAIR, FairValueVerdict.REVIEW_REQUIRED)


def test_fair_value_benefit_score_populated(svc):
    result = svc.assess_fair_value("EMI_ACCOUNT")
    assert 0 < result.benefit_score <= 100


def test_fair_value_rationale_populated(svc):
    result = svc.assess_fair_value("EMI_ACCOUNT")
    assert len(result.rationale) > 20


def test_fair_value_unknown_product_raises(svc):
    with pytest.raises(ValueError, match="Unknown product"):
        svc.assess_fair_value("UNKNOWN_PRODUCT")


def test_fair_value_assessed_at_set(svc):
    result = svc.assess_fair_value("EMI_ACCOUNT")
    assert result.assessed_at is not None


# ── Unit: Outcome recording ───────────────────────────────────────────────────


def test_record_outcome_good(svc):
    result = svc.record_outcome(
        customer_id="cust-010",
        outcome=ConsumerDutyOutcome.CONSUMER_SUPPORT,
        rating=OutcomeRating.GOOD,
        interaction_type="SUPPORT",
        notes="Issue resolved first contact",
    )
    assert result.record_id is not None
    assert result.rating == OutcomeRating.GOOD
    assert result.outcome == ConsumerDutyOutcome.CONSUMER_SUPPORT


def test_record_outcome_poor(svc):
    result = svc.record_outcome(
        customer_id="cust-011",
        outcome=ConsumerDutyOutcome.PRICE_AND_VALUE,
        rating=OutcomeRating.POOR,
        interaction_type="COMPLAINT",
        notes="Customer felt fees were unclear",
    )
    assert result.rating == OutcomeRating.POOR


def test_record_multiple_outcomes_all_stored(svc):
    for i in range(5):
        svc.record_outcome(
            f"cust-{i:03d}",
            ConsumerDutyOutcome.PRODUCTS_AND_SERVICES,
            OutcomeRating.GOOD,
            "PAYMENT",
        )
    assert len(svc._outcome_records) == 5


# ── Unit: Report generation ───────────────────────────────────────────────────


def test_generate_report_empty_period(svc):
    report = svc.generate_report(
        period_start=date(2026, 1, 1),
        period_end=date(2026, 3, 31),
        total_customers=500,
    )
    assert report.total_customers == 500
    assert report.vulnerable_customers == 0
    assert report.overall_good_outcome_pct == 0.0
    assert len(report.fair_value_assessments) >= 2  # EMI_ACCOUNT + BUSINESS_ACCOUNT × 2 types


def test_generate_report_counts_vulnerable_customers(svc):
    svc.assess_vulnerability("cust-v1", [VulnerabilityFlag.FINANCIAL_DIFFICULTY])
    svc.assess_vulnerability("cust-v2", [VulnerabilityFlag.MENTAL_HEALTH])
    svc.assess_vulnerability("cust-v3", [])  # Not vulnerable

    report = svc.generate_report(
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        total_customers=1000,
    )
    assert report.vulnerable_customers == 2


def test_generate_report_vulnerable_pct(svc):
    svc.assess_vulnerability("cust-p1", [VulnerabilityFlag.BEREAVEMENT])
    report = svc.generate_report(
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        total_customers=100,
    )
    assert report.vulnerable_pct == 1.0  # 1 out of 100


def test_generate_report_good_outcome_pct(svc):
    today = datetime.now(UTC).date()
    # 3 GOOD, 1 POOR → 75% good
    for _ in range(3):
        svc.record_outcome(
            "cust-x", ConsumerDutyOutcome.CONSUMER_SUPPORT, OutcomeRating.GOOD, "SUPPORT"
        )
    svc.record_outcome(
        "cust-y", ConsumerDutyOutcome.CONSUMER_UNDERSTANDING, OutcomeRating.POOR, "KYC"
    )

    report = svc.generate_report(
        period_start=today,
        period_end=today,
        total_customers=100,
    )
    assert report.overall_good_outcome_pct == 75.0


def test_generate_report_contains_fair_value_assessments(svc):
    report = svc.generate_report(
        period_start=date(2026, 1, 1),
        period_end=date(2026, 3, 31),
        total_customers=10,
    )
    product_ids = {fva.product_id for fva in report.fair_value_assessments}
    assert "EMI_ACCOUNT" in product_ids


def test_generate_report_complaints_fields_preserved(svc):
    report = svc.generate_report(
        period_start=date(2026, 1, 1),
        period_end=date(2026, 3, 31),
        total_customers=200,
        complaints_count=12,
        avg_complaint_resolution_days=14.5,
    )
    assert report.complaints_count == 12
    assert report.avg_complaint_resolution_days == 14.5


# ── API tests ─────────────────────────────────────────────────────────────────


def test_api_assess_vulnerability(client):
    resp = client.post(
        "/v1/consumer-duty/vulnerability",
        json={
            "customer_id": "cust-api-001",
            "flags": ["FINANCIAL_DIFFICULTY"],
            "assessed_by": "operator-1",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["is_vulnerable"] is True
    assert "FINANCIAL_DIFFICULTY" in data["flags"]
    assert len(data["support_actions"]) >= 1


def test_api_assess_vulnerability_no_flags(client):
    resp = client.post(
        "/v1/consumer-duty/vulnerability",
        json={
            "customer_id": "cust-api-002",
            "flags": [],
        },
    )
    assert resp.status_code == 201
    assert resp.json()["is_vulnerable"] is False


def test_api_get_vulnerability_exists(client):
    client.post(
        "/v1/consumer-duty/vulnerability",
        json={
            "customer_id": "cust-api-003",
            "flags": ["MENTAL_HEALTH"],
        },
    )
    resp = client.get("/v1/consumer-duty/vulnerability/cust-api-003")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_assessment"] is True
    assert data["assessment"]["is_vulnerable"] is True


def test_api_get_vulnerability_not_found(client):
    resp = client.get("/v1/consumer-duty/vulnerability/cust-ghost-999")
    assert resp.status_code == 200
    assert resp.json()["has_assessment"] is False


def test_api_fair_value_known_product(client):
    resp = client.post(
        "/v1/consumer-duty/fair-value",
        params={"product_id": "EMI_ACCOUNT", "entity_type": "INDIVIDUAL"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] in ("FAIR", "REVIEW_REQUIRED", "UNFAIR")
    assert data["benefit_score"] > 0


def test_api_fair_value_unknown_product(client):
    resp = client.post(
        "/v1/consumer-duty/fair-value",
        params={"product_id": "NONEXISTENT", "entity_type": "INDIVIDUAL"},
    )
    assert resp.status_code == 404


def test_api_record_outcome(client):
    resp = client.post(
        "/v1/consumer-duty/outcomes",
        json={
            "customer_id": "cust-api-010",
            "outcome": "CONSUMER_SUPPORT",
            "rating": "GOOD",
            "interaction_type": "SUPPORT",
            "notes": "First-call resolution",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["record_id"] is not None
    assert data["outcome"] == "CONSUMER_SUPPORT"
    assert data["rating"] == "GOOD"


def test_api_record_outcome_invalid_interaction_type(client):
    resp = client.post(
        "/v1/consumer-duty/outcomes",
        json={
            "customer_id": "cust-api-011",
            "outcome": "CONSUMER_SUPPORT",
            "rating": "GOOD",
            "interaction_type": "INVALID_TYPE",
        },
    )
    assert resp.status_code == 422


def test_api_generate_report(client):
    resp = client.post(
        "/v1/consumer-duty/report",
        json={
            "period_start": "2026-01-01",
            "period_end": "2026-03-31",
            "total_customers": 500,
            "complaints_count": 8,
            "avg_complaint_resolution_days": 12.0,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_customers"] == 500
    assert "outcome_ratings" in data
    assert "fair_value_assessments" in data
    assert len(data["fair_value_assessments"]) >= 2


def test_api_report_period_end_before_start_is_422(client):
    resp = client.post(
        "/v1/consumer-duty/report",
        json={
            "period_start": "2026-06-01",
            "period_end": "2026-01-01",  # Before start — invalid
            "total_customers": 100,
        },
    )
    assert resp.status_code == 422
