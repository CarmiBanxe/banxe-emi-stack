"""
tests/test_hitl_service.py — HITL Review Queue tests
IL-051 | Phase 2 #10 | banxe-emi-stack

Coverage:
  - Unit: enqueue, decide, list_queue, stats, feedback corpus, SLA, expiry
  - Integration: from_pipeline_result (FraudAMLPipeline → HITLService)
  - API: GET/POST queue, GET case, POST decide, GET stats
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routers.hitl import _get_hitl_service
from services.aml.tx_monitor import InMemoryVelocityTracker, TxMonitorService
from services.fraud.fraud_aml_pipeline import FraudAMLPipeline, PipelineRequest
from services.fraud.mock_fraud_adapter import MockFraudAdapter
from services.hitl.hitl_port import CaseStatus, DecisionOutcome, ReviewReason
from services.hitl.hitl_service import HITLCaseError, HITLService

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def svc():
    return HITLService()


@pytest.fixture
def client():
    fresh_svc = HITLService()
    app.dependency_overrides[_get_hitl_service] = lambda: fresh_svc
    _get_hitl_service.cache_clear()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    _get_hitl_service.cache_clear()


def _enqueue(svc: HITLService, **kwargs):
    defaults = dict(
        transaction_id="tx-001",
        customer_id="cust-001",
        entity_type="INDIVIDUAL",
        amount=Decimal("10000.00"),
        currency="GBP",
        reasons=[ReviewReason.EDD_REQUIRED],
        fraud_score=55,
        fraud_risk="MEDIUM",
        aml_flags=["EDD required"],
        hold_reasons=["Amount ≥ £10,000 EDD threshold"],
    )
    defaults.update(kwargs)
    return svc.enqueue(**defaults)


# ── Unit: enqueue ─────────────────────────────────────────────────────────────


def test_enqueue_creates_pending_case(svc):
    case = _enqueue(svc)
    assert case.status == CaseStatus.PENDING
    assert case.case_id is not None
    assert case.transaction_id == "tx-001"


def test_enqueue_generates_unique_case_ids(svc):
    c1 = _enqueue(svc, transaction_id="tx-001")
    c2 = _enqueue(svc, transaction_id="tx-002")
    assert c1.case_id != c2.case_id


def test_enqueue_standard_sla_24h(svc):
    case = _enqueue(svc, reasons=[ReviewReason.EDD_REQUIRED])
    delta_h = (case.expires_at - case.created_at).total_seconds() / 3600
    assert abs(delta_h - 24) < 0.01


def test_enqueue_sar_sla_4h(svc):
    case = _enqueue(svc, reasons=[ReviewReason.SAR_REQUIRED])
    delta_h = (case.expires_at - case.created_at).total_seconds() / 3600
    assert abs(delta_h - 4) < 0.01
    assert case.is_sar_case is True


def test_enqueue_non_sar_not_sar_case(svc):
    case = _enqueue(svc, reasons=[ReviewReason.FRAUD_HIGH])
    assert case.is_sar_case is False


def test_enqueue_case_stored_and_retrievable(svc):
    case = _enqueue(svc)
    retrieved = svc.get_case(case.case_id)
    assert retrieved is not None
    assert retrieved.case_id == case.case_id


def test_get_case_nonexistent_returns_none(svc):
    assert svc.get_case("nonexistent-uuid") is None


# ── Unit: decide ──────────────────────────────────────────────────────────────


def test_decide_approve(svc):
    case = _enqueue(svc)
    decided = svc.decide(case.case_id, DecisionOutcome.APPROVE, "op-001")
    assert decided.status == CaseStatus.APPROVED
    assert decided.decision == DecisionOutcome.APPROVE
    assert decided.decision_by == "op-001"
    assert decided.decided_at is not None


def test_decide_reject(svc):
    case = _enqueue(svc)
    decided = svc.decide(case.case_id, DecisionOutcome.REJECT, "op-002", "Suspicious payee")
    assert decided.status == CaseStatus.REJECTED
    assert decided.decision_notes == "Suspicious payee"


def test_decide_escalate(svc):
    case = _enqueue(svc, reasons=[ReviewReason.SAR_REQUIRED])
    decided = svc.decide(case.case_id, DecisionOutcome.ESCALATE, "op-003", "Needs MLRO")
    assert decided.status == CaseStatus.ESCALATED


def test_decide_nonexistent_case_raises(svc):
    with pytest.raises(HITLCaseError, match="not found"):
        svc.decide("bad-uuid", DecisionOutcome.APPROVE, "op-001")


def test_decide_already_decided_raises(svc):
    case = _enqueue(svc)
    svc.decide(case.case_id, DecisionOutcome.APPROVE, "op-001")
    with pytest.raises(HITLCaseError, match="already"):
        svc.decide(case.case_id, DecisionOutcome.REJECT, "op-002")


# ── Unit: list_queue ──────────────────────────────────────────────────────────


def test_list_queue_returns_all_by_default(svc):
    _enqueue(svc, transaction_id="tx-001")
    _enqueue(svc, transaction_id="tx-002")
    cases = svc.list_queue()
    assert len(cases) == 2


def test_list_queue_filter_pending(svc):
    c1 = _enqueue(svc, transaction_id="tx-001")
    c2 = _enqueue(svc, transaction_id="tx-002")
    svc.decide(c1.case_id, DecisionOutcome.APPROVE, "op-001")
    pending = svc.list_queue(status=CaseStatus.PENDING)
    assert len(pending) == 1
    assert pending[0].case_id == c2.case_id


def test_list_queue_sar_cases_sorted_first(svc):
    _enqueue(svc, transaction_id="tx-normal", reasons=[ReviewReason.EDD_REQUIRED])
    _enqueue(svc, transaction_id="tx-sar", reasons=[ReviewReason.SAR_REQUIRED])
    cases = svc.list_queue(status=CaseStatus.PENDING)
    assert cases[0].is_sar_case is True


def test_list_queue_expired_cases_auto_marked(svc):
    case = _enqueue(svc)
    # Manually backdating expires_at to force expiry
    case.expires_at = datetime.now(UTC) - timedelta(hours=1)
    cases = svc.list_queue()
    expired = [c for c in cases if c.status == CaseStatus.EXPIRED]
    assert len(expired) == 1


# ── Unit: stats ───────────────────────────────────────────────────────────────


def test_stats_empty_service(svc):
    s = svc.stats()
    assert s.total_cases == 0
    assert s.pending_cases == 0
    assert s.approval_rate == 0.0
    assert s.avg_resolution_hours == 0.0


def test_stats_counts_correct(svc):
    c1 = _enqueue(svc, transaction_id="tx-1")
    c2 = _enqueue(svc, transaction_id="tx-2")
    _enqueue(svc, transaction_id="tx-3")
    svc.decide(c1.case_id, DecisionOutcome.APPROVE, "op-1")
    svc.decide(c2.case_id, DecisionOutcome.REJECT, "op-2")
    s = svc.stats()
    assert s.total_cases == 3
    assert s.pending_cases == 1
    assert s.approved_cases == 1
    assert s.rejected_cases == 1


def test_stats_approval_rate(svc):
    c1 = _enqueue(svc, transaction_id="tx-1")
    c2 = _enqueue(svc, transaction_id="tx-2")
    c3 = _enqueue(svc, transaction_id="tx-3")
    svc.decide(c1.case_id, DecisionOutcome.APPROVE, "op")
    svc.decide(c2.case_id, DecisionOutcome.APPROVE, "op")
    svc.decide(c3.case_id, DecisionOutcome.REJECT, "op")
    assert svc.stats().approval_rate == pytest.approx(66.7, abs=0.1)


# ── Unit: feedback corpus (I-27) ──────────────────────────────────────────────


def test_feedback_corpus_written_on_decide(svc):
    case = _enqueue(svc)
    svc.decide(case.case_id, DecisionOutcome.APPROVE, "op-001", "Looks clean")
    corpus = svc.get_feedback_corpus()
    assert len(corpus) == 1
    record = corpus[0]
    assert record["outcome"] == "APPROVE"
    assert record["decided_by"] == "op-001"
    assert record["notes"] == "Looks clean"
    assert "transaction_id" in record


def test_feedback_corpus_not_written_on_enqueue(svc):
    _enqueue(svc)
    assert len(svc.get_feedback_corpus()) == 0


def test_feedback_corpus_accumulates_decisions(svc):
    c1 = _enqueue(svc, transaction_id="tx-1")
    c2 = _enqueue(svc, transaction_id="tx-2")
    svc.decide(c1.case_id, DecisionOutcome.APPROVE, "op")
    svc.decide(c2.case_id, DecisionOutcome.REJECT, "op")
    assert len(svc.get_feedback_corpus()) == 2


# ── Integration: from_pipeline_result ─────────────────────────────────────────


def test_from_pipeline_result_edd_hold(svc):
    """INDIVIDUAL £10k → EDD HOLD → correctly maps to EDD_REQUIRED reason."""
    pipeline = FraudAMLPipeline(
        fraud_adapter=MockFraudAdapter(),
        tx_monitor=TxMonitorService(InMemoryVelocityTracker()),
    )
    result = pipeline.assess(
        PipelineRequest(
            transaction_id="tx-pipeline-001",
            customer_id="cust-pipeline-001",
            entity_type="INDIVIDUAL",
            amount=Decimal("10000.00"),
            currency="GBP",
            destination_account="GB29NWBK60161331926819",
            destination_sort_code="60-16-13",
            destination_country="GB",
            payment_rail="FPS",
            first_transaction_to_payee=False,
        )
    )
    # Must be HOLD for HITL to make sense
    from services.fraud.fraud_aml_pipeline import PipelineDecision

    assert result.decision == PipelineDecision.HOLD

    case = HITLService.from_pipeline_result(result, svc)
    assert case.status == CaseStatus.PENDING
    assert case.transaction_id == "tx-pipeline-001"
    assert ReviewReason.EDD_REQUIRED in case.reasons


# ── API tests ─────────────────────────────────────────────────────────────────


def _enqueue_payload(**kwargs):
    defaults = {
        "transaction_id": "tx-api-001",
        "customer_id": "cust-api-001",
        "amount": "10000.00",
        "reasons": ["EDD_REQUIRED"],
        "fraud_score": 55,
        "fraud_risk": "MEDIUM",
    }
    defaults.update(kwargs)
    return defaults


def test_api_enqueue_case(client):
    resp = client.post("/v1/hitl/queue", json=_enqueue_payload())
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "PENDING"
    assert data["case_id"] is not None
    assert data["is_sar_case"] is False


def test_api_enqueue_sar_case(client):
    resp = client.post(
        "/v1/hitl/queue",
        json=_enqueue_payload(reasons=["SAR_REQUIRED"], transaction_id="tx-sar-001"),
    )
    assert resp.status_code == 201
    assert resp.json()["is_sar_case"] is True
    assert resp.json()["hours_remaining"] <= 4.1


def test_api_get_queue_empty(client):
    resp = client.get("/v1/hitl/queue")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_api_get_queue_with_cases(client):
    client.post("/v1/hitl/queue", json=_enqueue_payload(transaction_id="tx-1"))
    client.post("/v1/hitl/queue", json=_enqueue_payload(transaction_id="tx-2"))
    resp = client.get("/v1/hitl/queue")
    assert resp.json()["total"] == 2
    assert resp.json()["pending"] == 2


def test_api_get_case_by_id(client):
    resp = client.post("/v1/hitl/queue", json=_enqueue_payload())
    case_id = resp.json()["case_id"]
    resp2 = client.get(f"/v1/hitl/queue/{case_id}")
    assert resp2.status_code == 200
    assert resp2.json()["case_id"] == case_id


def test_api_get_case_not_found(client):
    resp = client.get("/v1/hitl/queue/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_api_decide_approve(client):
    enq = client.post("/v1/hitl/queue", json=_enqueue_payload())
    case_id = enq.json()["case_id"]
    resp = client.post(
        f"/v1/hitl/queue/{case_id}/decide",
        json={
            "outcome": "APPROVE",
            "decided_by": "op-ceo",
            "notes": "Verified customer",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "APPROVED"
    assert resp.json()["decision_by"] == "op-ceo"


def test_api_decide_reject(client):
    enq = client.post("/v1/hitl/queue", json=_enqueue_payload())
    case_id = enq.json()["case_id"]
    resp = client.post(
        f"/v1/hitl/queue/{case_id}/decide",
        json={
            "outcome": "REJECT",
            "decided_by": "op-mlro",
            "notes": "Cannot verify source of funds",
        },
    )
    assert resp.json()["status"] == "REJECTED"


def test_api_decide_already_decided_returns_409(client):
    enq = client.post("/v1/hitl/queue", json=_enqueue_payload())
    case_id = enq.json()["case_id"]
    client.post(
        f"/v1/hitl/queue/{case_id}/decide", json={"outcome": "APPROVE", "decided_by": "op-1"}
    )
    resp = client.post(
        f"/v1/hitl/queue/{case_id}/decide", json={"outcome": "REJECT", "decided_by": "op-2"}
    )
    assert resp.status_code == 409


def test_api_get_stats(client):
    resp = client.get("/v1/hitl/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_cases" in data
    assert "approval_rate" in data
    assert "oldest_pending_hours" in data


def test_api_get_stats_after_decisions(client):
    enq1 = client.post("/v1/hitl/queue", json=_enqueue_payload(transaction_id="tx-s1"))
    enq2 = client.post("/v1/hitl/queue", json=_enqueue_payload(transaction_id="tx-s2"))
    client.post(
        f"/v1/hitl/queue/{enq1.json()['case_id']}/decide",
        json={"outcome": "APPROVE", "decided_by": "op"},
    )
    client.post(
        f"/v1/hitl/queue/{enq2.json()['case_id']}/decide",
        json={"outcome": "REJECT", "decided_by": "op"},
    )
    stats = client.get("/v1/hitl/stats").json()
    assert stats["approved_cases"] == 1
    assert stats["rejected_cases"] == 1
    assert stats["approval_rate"] == 50.0
