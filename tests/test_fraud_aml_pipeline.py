"""
tests/test_fraud_aml_pipeline.py — Fraud + AML Pipeline tests
IL-049 | S9-05 | banxe-emi-stack

Coverage:
  - Unit tests: FraudAMLPipeline.assess() decision matrix
  - Dual-entity thresholds (INDIVIDUAL vs COMPANY)
  - All BLOCK / HOLD / APPROVE paths
  - Integration: API POST /v1/fraud/assess
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routers.fraud import _get_pipeline
from services.aml.tx_monitor import InMemoryVelocityTracker, TxMonitorService
from services.fraud.fraud_aml_pipeline import (
    FraudAMLPipeline,
    PipelineDecision,
    PipelineRequest,
)
from services.fraud.mock_fraud_adapter import MockFraudAdapter


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pipeline() -> FraudAMLPipeline:
    """Fresh pipeline for each test — isolated velocity state."""
    return FraudAMLPipeline(
        fraud_adapter=MockFraudAdapter(),
        tx_monitor=TxMonitorService(InMemoryVelocityTracker()),
    )


def _req(**kwargs) -> PipelineRequest:
    defaults = dict(
        transaction_id="tx-001",
        customer_id="cust-001",
        entity_type="INDIVIDUAL",
        amount=Decimal("500.00"),
        currency="GBP",
        destination_account="GB29NWBK60161331926819",
        destination_sort_code="60-16-13",
        destination_country="GB",
        payment_rail="FPS",
        first_transaction_to_payee=False,
        amount_unusual=False,
        is_pep=False,
        is_sanctions_hit=False,
        is_fx=False,
    )
    defaults.update(kwargs)
    return PipelineRequest(**defaults)


# ── Unit: APPROVE paths ───────────────────────────────────────────────────────

def test_approve_low_risk_normal_transaction():
    result = _pipeline().assess(_req())
    assert result.decision == PipelineDecision.APPROVE
    assert result.approved is True
    assert not result.block_reasons
    assert not result.hold_reasons
    assert result.requires_hitl is False


def test_approve_medium_risk_no_aml_flags():
    """MEDIUM fraud (score 40-69) without AML flags → APPROVE."""
    result = _pipeline().assess(_req(
        amount=Decimal("2000.00"),
        first_transaction_to_payee=False,
    ))
    # MockFraudAdapter: £2000 known payee = MEDIUM (score=40), no HOLD
    assert result.decision == PipelineDecision.APPROVE
    assert result.fraud_risk.value == "MEDIUM"


# ── Unit: BLOCK paths ─────────────────────────────────────────────────────────

def test_block_fraud_critical_blocked_country():
    result = _pipeline().assess(_req(destination_country="RU"))
    assert result.decision == PipelineDecision.BLOCK
    assert result.requires_hitl is True
    assert len(result.block_reasons) >= 1
    assert "Fraud CRITICAL" in result.block_reasons[0]


def test_block_fraud_critical_high_value():
    """Amount ≥ £100,000 → fraud CRITICAL → BLOCK."""
    result = _pipeline().assess(_req(amount=Decimal("100000.00")))
    assert result.decision == PipelineDecision.BLOCK
    assert result.fraud_score >= 85


def test_block_sanctions_hit():
    """is_sanctions_hit=True → AML sanctions_block=True → BLOCK."""
    result = _pipeline().assess(_req(is_sanctions_hit=True))
    assert result.decision == PipelineDecision.BLOCK
    assert result.aml_sanctions_block is True
    assert any("sanctions" in r.lower() or "Sanctions" in r for r in result.block_reasons)


def test_block_beats_hold_when_both_present():
    """Fraud CRITICAL + EDD → decision is BLOCK, not HOLD."""
    result = _pipeline().assess(_req(
        destination_country="RU",    # CRITICAL
        amount=Decimal("15000.00"),  # Also EDD
    ))
    assert result.decision == PipelineDecision.BLOCK


def test_block_all_sanctioned_countries():
    """Every Category A country should trigger BLOCK via fraud scoring."""
    for country in ["RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE"]:
        result = _pipeline().assess(_req(destination_country=country))
        assert result.decision == PipelineDecision.BLOCK, (
            f"Expected BLOCK for {country}"
        )


# ── Unit: HOLD paths ──────────────────────────────────────────────────────────

def test_hold_fraud_high_risk():
    """Fraud HIGH (score 70-84) → HOLD, not BLOCK."""
    # £10,000 + first_to_payee = score 70 (HIGH)
    result = _pipeline().assess(_req(
        amount=Decimal("10000.00"),
        first_transaction_to_payee=True,
    ))
    assert result.decision == PipelineDecision.HOLD
    assert result.fraud_risk.value == "HIGH"
    assert result.requires_hitl is True
    assert not result.block_reasons
    assert len(result.hold_reasons) >= 1


def test_hold_app_scam_investment():
    """APP scam signal (PSR APP 2024) → HOLD."""
    result = _pipeline().assess(_req(
        amount=Decimal("15000.00"),
        first_transaction_to_payee=True,
        amount_unusual=True,
        entity_type="INDIVIDUAL",
    ))
    assert result.decision in (PipelineDecision.HOLD, PipelineDecision.BLOCK)
    # APP scam indicator should be set
    assert result.app_scam_indicator.value != "NONE"


def test_hold_edd_required_individual():
    """INDIVIDUAL £10,000 → EDD required → HOLD."""
    result = _pipeline().assess(_req(
        amount=Decimal("10000.00"),
        first_transaction_to_payee=False,  # Keep fraud LOW
    ))
    # Fraud: £10k known payee = HIGH (score=50), holds for review
    assert result.aml_edd_required is True
    assert result.decision in (PipelineDecision.HOLD, PipelineDecision.BLOCK)


def test_hold_sar_required_individual():
    """INDIVIDUAL £50,000 → SAR consideration → HOLD."""
    result = _pipeline().assess(_req(amount=Decimal("50000.00")))
    assert result.aml_sar_required is True
    assert result.decision in (PipelineDecision.HOLD, PipelineDecision.BLOCK)


def test_hold_velocity_daily_breach():
    """Pre-load daily velocity to breach limit, then assess → HOLD."""
    tracker = InMemoryVelocityTracker()
    pipeline = FraudAMLPipeline(
        fraud_adapter=MockFraudAdapter(),
        tx_monitor=TxMonitorService(tracker),
    )
    # Pre-load £24,000 (INDIVIDUAL daily limit = £25,000)
    for _ in range(3):
        tracker.record("cust-vel", Decimal("8000.00"))

    result = pipeline.assess(_req(
        customer_id="cust-vel",
        amount=Decimal("2000.00"),    # total: £26,000 → breach
    ))
    assert result.aml_velocity_daily_breach is True
    assert result.decision in (PipelineDecision.HOLD, PipelineDecision.BLOCK)


def test_hold_structuring_signal():
    """3 sub-threshold txs totalling ≥ £9,000 → structuring → HOLD."""
    tracker = InMemoryVelocityTracker()
    pipeline = FraudAMLPipeline(
        fraud_adapter=MockFraudAdapter(),
        tx_monitor=TxMonitorService(tracker),
    )
    tracker.record("cust-struct", Decimal("3000.00"))
    tracker.record("cust-struct", Decimal("3000.00"))

    result = pipeline.assess(_req(
        customer_id="cust-struct",
        amount=Decimal("3500.00"),  # 3rd tx → 3 txs, £9,500 total
    ))
    assert result.aml_structuring_signal is True
    assert result.decision in (PipelineDecision.HOLD, PipelineDecision.BLOCK)


# ── Unit: Dual-entity thresholds ──────────────────────────────────────────────

def test_company_30k_below_edd_threshold():
    """COMPANY: EDD trigger = £50,000 → £30,000 has no EDD flag."""
    result = _pipeline().assess(_req(
        entity_type="COMPANY",
        amount=Decimal("30000.00"),
        first_transaction_to_payee=False,
    ))
    assert result.aml_edd_required is False


def test_individual_10k_triggers_edd():
    """INDIVIDUAL: EDD trigger = £10,000 → exact threshold triggers EDD."""
    result = _pipeline().assess(_req(
        entity_type="INDIVIDUAL",
        amount=Decimal("10000.00"),
        first_transaction_to_payee=False,
    ))
    assert result.aml_edd_required is True


def test_company_50k_triggers_edd():
    """COMPANY: EDD trigger = £50,000 → exact threshold triggers EDD."""
    result = _pipeline().assess(_req(
        entity_type="COMPANY",
        amount=Decimal("50000.00"),
        first_transaction_to_payee=False,
    ))
    assert result.aml_edd_required is True


# ── Unit: Result metadata ─────────────────────────────────────────────────────

def test_result_assessed_at_is_set():
    result = _pipeline().assess(_req())
    assert result.assessed_at is not None


def test_result_fraud_latency_positive():
    result = _pipeline().assess(_req())
    assert result.fraud_latency_ms >= 0


def test_result_contains_fraud_factors_on_risk():
    result = _pipeline().assess(_req(
        amount=Decimal("10000.00"),
        first_transaction_to_payee=True,
    ))
    assert len(result.fraud_factors) > 0


def test_result_contains_aml_reasons_on_flags():
    result = _pipeline().assess(_req(amount=Decimal("10000.00")))
    assert len(result.aml_reasons) > 0


# ── API tests ─────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    fresh_pipeline = FraudAMLPipeline(
        fraud_adapter=MockFraudAdapter(),
        tx_monitor=TxMonitorService(InMemoryVelocityTracker()),
    )
    app.dependency_overrides[_get_pipeline] = lambda: fresh_pipeline
    _get_pipeline.cache_clear()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    _get_pipeline.cache_clear()


def _payload(**kwargs):
    defaults = {
        "transaction_id": "tx-api-001",
        "customer_id": "cust-api-001",
        "entity_type": "INDIVIDUAL",
        "amount": "500.00",
        "currency": "GBP",
        "destination_account": "GB29NWBK60161331926819",
        "destination_sort_code": "60-16-13",
        "destination_country": "GB",
        "payment_rail": "FPS",
    }
    defaults.update(kwargs)
    return defaults


def test_api_assess_approve(client):
    resp = client.post("/v1/fraud/assess", json=_payload())
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "APPROVE"
    assert data["requires_hitl"] is False
    assert "transaction_id" in data


def test_api_assess_block_sanctions(client):
    resp = client.post("/v1/fraud/assess", json=_payload(
        is_sanctions_hit=True,
        amount="500.00",
    ))
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "BLOCK"
    assert data["aml_sanctions_block"] is True


def test_api_assess_hold_edd(client):
    resp = client.post("/v1/fraud/assess", json=_payload(
        amount="10000.00",
        first_transaction_to_payee=False,
    ))
    assert resp.status_code == 200
    data = resp.json()
    assert data["aml_edd_required"] is True
    assert data["decision"] in ("HOLD", "BLOCK")


def test_api_assess_invalid_amount(client):
    resp = client.post("/v1/fraud/assess", json=_payload(amount="not-a-number"))
    assert resp.status_code == 422


def test_api_assess_invalid_country(client):
    resp = client.post("/v1/fraud/assess", json=_payload(destination_country="GBR"))
    assert resp.status_code == 422


def test_api_assess_invalid_entity_type(client):
    resp = client.post("/v1/fraud/assess", json=_payload(entity_type="PERSON"))
    assert resp.status_code == 422


def test_api_assess_response_contains_all_fields(client):
    resp = client.post("/v1/fraud/assess", json=_payload())
    assert resp.status_code == 200
    data = resp.json()
    required_fields = [
        "decision", "fraud_risk", "fraud_score", "app_scam_indicator",
        "fraud_factors", "aml_edd_required", "aml_sanctions_block",
        "block_reasons", "hold_reasons", "requires_hitl", "assessed_at",
    ]
    for f in required_fields:
        assert f in data, f"Missing field: {f}"
