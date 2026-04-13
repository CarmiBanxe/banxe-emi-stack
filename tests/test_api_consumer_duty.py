"""
tests/test_api_consumer_duty.py — Consumer Duty router tests
S13-06-FIX-4 | banxe-emi-stack

Tests for POST/GET /v1/consumer-duty/* endpoints (consumer_duty.py 46% → ≥85%).
consumer_duty.py uses @lru_cache, NOT FastAPI Depends.
Patch: unittest.mock.patch("api.routers.consumer_duty._get_consumer_duty_service")
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import pytest

from api.main import app
from services.consumer_duty.consumer_duty_port import (
    ConsumerDutyOutcome,
    ConsumerDutyReport,
    FairValueAssessment,
    FairValueVerdict,
    OutcomeRating,
    OutcomeRecord,
    VulnerabilityAssessment,
    VulnerabilityCategory,
    VulnerabilityFlag,
)

client = TestClient(app)

_MODULE = "api.routers.consumer_duty._get_consumer_duty_service"


# ── Helpers ────────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(UTC)


def _make_vuln_assessment(customer_id: str = "cust-001") -> VulnerabilityAssessment:
    return VulnerabilityAssessment(
        customer_id=customer_id,
        flags=[VulnerabilityFlag.FINANCIAL_DIFFICULTY],
        categories=[VulnerabilityCategory.RESILIENCE],
        support_actions=["Simplified communications sent", "Debt guidance offered"],
        is_vulnerable=True,
        assessed_at=_now(),
        assessed_by="system",
        notes="Auto-flagged via KYC enrichment.",
    )


def _make_fair_value() -> FairValueAssessment:
    return FairValueAssessment(
        product_id="emoney-account",
        entity_type="INDIVIDUAL",
        annual_fee_estimate=Decimal("120.00"),
        benchmark_annual_fee=Decimal("150.00"),
        benefit_score=78,
        verdict=FairValueVerdict.FAIR,
        rationale="Annual fee is 20% below UK EMI benchmark. Benefit score 78/100.",
        assessed_at=_now(),
    )


def _make_outcome_record() -> OutcomeRecord:
    return OutcomeRecord(
        record_id="rec-001",
        customer_id="cust-001",
        outcome=ConsumerDutyOutcome.CONSUMER_SUPPORT,
        rating=OutcomeRating.GOOD,
        interaction_type="SUPPORT",
        notes="Issue resolved within SLA.",
    )


def _make_report() -> ConsumerDutyReport:
    return ConsumerDutyReport(
        period_start=date(2026, 1, 1),
        period_end=date(2026, 3, 31),
        generated_at=_now(),
        total_customers=1000,
        vulnerable_customers=50,
        outcome_ratings={
            "CONSUMER_SUPPORT": {"GOOD": 800, "NEUTRAL": 150, "POOR": 50},
        },
        fair_value_assessments=[_make_fair_value()],
        complaints_count=10,
        avg_complaint_resolution_days=4.5,
    )


# ── Fixture ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def mock_svc():
    """Patch _get_consumer_duty_service (lru_cached) for every test."""
    from api.routers.consumer_duty import _get_consumer_duty_service

    _get_consumer_duty_service.cache_clear()
    m = MagicMock()
    m.assess_vulnerability.return_value = _make_vuln_assessment()
    m.get_vulnerability.return_value = _make_vuln_assessment()
    m.assess_fair_value.return_value = _make_fair_value()
    m.record_outcome.return_value = _make_outcome_record()
    m.generate_report.return_value = _make_report()

    with patch(_MODULE, return_value=m):
        yield m

    _get_consumer_duty_service.cache_clear()


# ── Vulnerability (POST) ───────────────────────────────────────────────────


def test_assess_vulnerability_returns_201():
    resp = client.post(
        "/v1/consumer-duty/vulnerability",
        json={
            "customer_id": "cust-001",
            "flags": ["FINANCIAL_DIFFICULTY"],
            "assessed_by": "system",
        },
    )
    assert resp.status_code == 201


def test_assess_vulnerability_response_has_is_vulnerable():
    resp = client.post(
        "/v1/consumer-duty/vulnerability",
        json={"customer_id": "cust-001", "flags": ["FINANCIAL_DIFFICULTY"]},
    )
    data = resp.json()
    assert "is_vulnerable" in data
    assert data["is_vulnerable"] is True


def test_assess_vulnerability_response_has_support_actions():
    resp = client.post(
        "/v1/consumer-duty/vulnerability",
        json={"customer_id": "cust-001", "flags": ["MENTAL_HEALTH"]},
    )
    data = resp.json()
    assert "support_actions" in data
    assert isinstance(data["support_actions"], list)


# ── Vulnerability (GET) ────────────────────────────────────────────────────


def test_get_vulnerability_with_assessment_returns_200():
    resp = client.get("/v1/consumer-duty/vulnerability/cust-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_assessment"] is True
    assert data["customer_id"] == "cust-001"


def test_get_vulnerability_no_assessment_returns_200(mock_svc):
    mock_svc.get_vulnerability.return_value = None
    resp = client.get("/v1/consumer-duty/vulnerability/cust-new")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_assessment"] is False
    assert data["assessment"] is None


# ── Fair value ─────────────────────────────────────────────────────────────


def test_assess_fair_value_returns_200():
    resp = client.post(
        "/v1/consumer-duty/fair-value?product_id=emoney-account&entity_type=INDIVIDUAL"
    )
    assert resp.status_code == 200


def test_assess_fair_value_response_has_verdict():
    resp = client.post(
        "/v1/consumer-duty/fair-value?product_id=emoney-account&entity_type=INDIVIDUAL"
    )
    data = resp.json()
    assert data["verdict"] == "FAIR"
    assert data["product_id"] == "emoney-account"


def test_assess_fair_value_unknown_product_returns_404(mock_svc):
    mock_svc.assess_fair_value.side_effect = ValueError("Product 'unknown-prod' not found")
    resp = client.post(
        "/v1/consumer-duty/fair-value?product_id=unknown-prod&entity_type=INDIVIDUAL"
    )
    assert resp.status_code == 404


# ── Outcomes ───────────────────────────────────────────────────────────────


def test_record_outcome_returns_201():
    resp = client.post(
        "/v1/consumer-duty/outcomes",
        json={
            "customer_id": "cust-001",
            "outcome": "CONSUMER_SUPPORT",
            "rating": "GOOD",
            "interaction_type": "SUPPORT",
            "notes": "Resolved within SLA.",
        },
    )
    assert resp.status_code == 201


def test_record_outcome_response_has_record_id():
    resp = client.post(
        "/v1/consumer-duty/outcomes",
        json={
            "customer_id": "cust-001",
            "outcome": "CONSUMER_SUPPORT",
            "rating": "GOOD",
            "interaction_type": "SUPPORT",
        },
    )
    data = resp.json()
    assert data["record_id"] == "rec-001"


# ── Report ─────────────────────────────────────────────────────────────────


def test_generate_report_returns_200():
    resp = client.post(
        "/v1/consumer-duty/report",
        json={
            "period_start": "2026-01-01",
            "period_end": "2026-03-31",
            "total_customers": 1000,
            "complaints_count": 10,
            "avg_complaint_resolution_days": 4.5,
        },
    )
    assert resp.status_code == 200


def test_generate_report_response_has_vulnerable_pct():
    resp = client.post(
        "/v1/consumer-duty/report",
        json={
            "period_start": "2026-01-01",
            "period_end": "2026-03-31",
            "total_customers": 1000,
            "complaints_count": 10,
        },
    )
    data = resp.json()
    assert "vulnerable_pct" in data
    assert "overall_good_outcome_pct" in data
    assert "fair_value_assessments" in data
