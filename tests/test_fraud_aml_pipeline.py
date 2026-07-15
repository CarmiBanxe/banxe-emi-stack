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

from fastapi.testclient import TestClient
import httpx
import pytest

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
    result = _pipeline().assess(
        _req(
            amount=Decimal("2000.00"),
            first_transaction_to_payee=False,
        )
    )
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
    result = _pipeline().assess(
        _req(
            destination_country="RU",  # CRITICAL
            amount=Decimal("15000.00"),  # Also EDD
        )
    )
    assert result.decision == PipelineDecision.BLOCK


def test_block_all_sanctioned_countries():
    """Every Category A country should trigger BLOCK via fraud scoring."""
    for country in ["RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE"]:
        result = _pipeline().assess(_req(destination_country=country))
        assert result.decision == PipelineDecision.BLOCK, f"Expected BLOCK for {country}"


# ── Unit: HOLD paths ──────────────────────────────────────────────────────────


def test_hold_fraud_high_risk():
    """Fraud HIGH (score 70-84) → HOLD, not BLOCK."""
    # £10,000 + first_to_payee = score 70 (HIGH)
    result = _pipeline().assess(
        _req(
            amount=Decimal("10000.00"),
            first_transaction_to_payee=True,
        )
    )
    assert result.decision == PipelineDecision.HOLD
    assert result.fraud_risk.value == "HIGH"
    assert result.requires_hitl is True
    assert not result.block_reasons
    assert len(result.hold_reasons) >= 1


def test_hold_app_scam_investment():
    """APP scam signal (PSR APP 2024) → HOLD."""
    result = _pipeline().assess(
        _req(
            amount=Decimal("15000.00"),
            first_transaction_to_payee=True,
            amount_unusual=True,
            entity_type="INDIVIDUAL",
        )
    )
    assert result.decision in (PipelineDecision.HOLD, PipelineDecision.BLOCK)
    # APP scam indicator should be set
    assert result.app_scam_indicator.value != "NONE"


def test_hold_edd_required_individual():
    """INDIVIDUAL £10,000 → EDD required → HOLD."""
    result = _pipeline().assess(
        _req(
            amount=Decimal("10000.00"),
            first_transaction_to_payee=False,  # Keep fraud LOW
        )
    )
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

    result = pipeline.assess(
        _req(
            customer_id="cust-vel",
            amount=Decimal("2000.00"),  # total: £26,000 → breach
        )
    )
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

    result = pipeline.assess(
        _req(
            customer_id="cust-struct",
            amount=Decimal("3500.00"),  # 3rd tx → 3 txs, £9,500 total
        )
    )
    assert result.aml_structuring_signal is True
    assert result.decision in (PipelineDecision.HOLD, PipelineDecision.BLOCK)


# ── Unit: Dual-entity thresholds ──────────────────────────────────────────────


def test_company_30k_below_edd_threshold():
    """COMPANY: EDD trigger = £50,000 → £30,000 has no EDD flag."""
    result = _pipeline().assess(
        _req(
            entity_type="COMPANY",
            amount=Decimal("30000.00"),
            first_transaction_to_payee=False,
        )
    )
    assert result.aml_edd_required is False


def test_individual_10k_triggers_edd():
    """INDIVIDUAL: EDD trigger = £10,000 → exact threshold triggers EDD."""
    result = _pipeline().assess(
        _req(
            entity_type="INDIVIDUAL",
            amount=Decimal("10000.00"),
            first_transaction_to_payee=False,
        )
    )
    assert result.aml_edd_required is True


def test_company_50k_triggers_edd():
    """COMPANY: EDD trigger = £50,000 → exact threshold triggers EDD."""
    result = _pipeline().assess(
        _req(
            entity_type="COMPANY",
            amount=Decimal("50000.00"),
            first_transaction_to_payee=False,
        )
    )
    assert result.aml_edd_required is True


# ── Unit: Result metadata ─────────────────────────────────────────────────────


def test_result_assessed_at_is_set():
    result = _pipeline().assess(_req())
    assert result.assessed_at is not None


def test_result_fraud_latency_positive():
    result = _pipeline().assess(_req())
    assert result.fraud_latency_ms >= 0


def test_result_contains_fraud_factors_on_risk():
    result = _pipeline().assess(
        _req(
            amount=Decimal("10000.00"),
            first_transaction_to_payee=True,
        )
    )
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
    resp = client.post(
        "/v1/fraud/assess",
        json=_payload(
            is_sanctions_hit=True,
            amount="500.00",
        ),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "BLOCK"
    assert data["aml_sanctions_block"] is True


def test_api_assess_hold_edd(client):
    resp = client.post(
        "/v1/fraud/assess",
        json=_payload(
            amount="10000.00",
            first_transaction_to_payee=False,
        ),
    )
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
        "decision",
        "fraud_risk",
        "fraud_score",
        "app_scam_indicator",
        "fraud_factors",
        "aml_edd_required",
        "aml_sanctions_block",
        "block_reasons",
        "hold_reasons",
        "requires_hitl",
        "assessed_at",
    ]
    for f in required_fields:
        assert f in data, f"Missing field: {f}"


# ══════════════════════════════════════════════════════════════════════════════
# IL-049 coverage extension — SARService + RedisVelocityTracker (unit)
# Appended tests only; existing tests above are unchanged.
# ══════════════════════════════════════════════════════════════════════════════


# ── redis_velocity_tracker.py ─────────────────────────────────────────────────


def _fake_redis():
    from unittest.mock import MagicMock

    return MagicMock()


def _tracker(redis_client):
    from services.aml.redis_velocity_tracker import RedisVelocityTracker

    return RedisVelocityTracker(redis_client)


def test_rvt_get_compliance_context_branches():
    """Cover get_compliance_context both branches without touching the network."""
    from services.aml import redis_velocity_tracker as rvt

    prev_avail = rvt._RAG_AVAILABLE
    prev_ctx = rvt._rag_context
    try:
        rvt._RAG_AVAILABLE = False
        assert rvt.get_compliance_context("q") == ""
        rvt._RAG_AVAILABLE = True
        rvt._rag_context = lambda agent, query, k=3: "ctx"
        assert rvt.get_compliance_context("q", agent_name="a") == "ctx"
    finally:
        rvt._RAG_AVAILABLE = prev_avail
        rvt._rag_context = prev_ctx


def test_rvt_record_success():
    redis_client = _fake_redis()
    tracker = _tracker(redis_client)
    tracker.record("cust-1", Decimal("100.00"))
    redis_client.pipeline.assert_called_once_with(transaction=False)
    pipe = redis_client.pipeline.return_value
    assert pipe.zadd.called
    assert pipe.expire.called
    assert pipe.execute.called


def test_rvt_record_error_raises():
    from services.aml.redis_velocity_tracker import RedisVelocityTrackerError

    redis_client = _fake_redis()
    redis_client.pipeline.side_effect = RuntimeError("redis down")
    tracker = _tracker(redis_client)
    with pytest.raises(RedisVelocityTrackerError):
        tracker.record("cust-1", Decimal("100.00"))


def test_rvt_query_windows_sum_and_count():
    redis_client = _fake_redis()
    redis_client.zrangebyscore.return_value = [b"uuid-a:100.00", b"uuid-b:50.50"]
    tracker = _tracker(redis_client)

    total, count = tracker.get_daily("cust-1")
    assert total == Decimal("150.50")
    assert count == 2

    total, count = tracker.get_monthly("cust-1")
    assert total == Decimal("150.50")
    assert count == 2

    total, count = tracker.get_recent_window("cust-1", hours=6)
    assert total == Decimal("150.50")
    assert count == 2


def test_rvt_query_error_raises():
    from services.aml.redis_velocity_tracker import RedisVelocityTrackerError

    redis_client = _fake_redis()
    redis_client.zrangebyscore.side_effect = RuntimeError("redis down")
    tracker = _tracker(redis_client)
    with pytest.raises(RedisVelocityTrackerError):
        tracker.get_daily("cust-1")


def test_rvt_reset_success_and_error():
    from services.aml.redis_velocity_tracker import RedisVelocityTrackerError

    redis_client = _fake_redis()
    tracker = _tracker(redis_client)
    tracker.reset("cust-1")
    redis_client.delete.assert_called_once_with("banxe:velocity:cust-1")

    redis_client.delete.side_effect = RuntimeError("redis down")
    with pytest.raises(RedisVelocityTrackerError):
        tracker.reset("cust-1")


def test_rvt_health_true_and_false():
    redis_client = _fake_redis()
    redis_client.ping.return_value = True
    assert _tracker(redis_client).health() is True

    redis_client.ping.side_effect = RuntimeError("no ping")
    assert _tracker(redis_client).health() is False


# ── sar_service.py — domain types & helpers ───────────────────────────────────


def _sample_reasons():
    from services.aml.sar_service import SARReason

    return [SARReason.VELOCITY_BREACH, SARReason.STRUCTURING]


def _file_draft(service, customer_id="cust-1"):
    return service.file_sar(
        transaction_id="tx-1",
        customer_id=customer_id,
        entity_type="INDIVIDUAL",
        amount=Decimal("12000.00"),
        currency="GBP",
        sar_reasons=_sample_reasons(),
        aml_flags=["aml_velocity_daily_breach"],
        fraud_score=72,
    )


def test_sar_get_compliance_context_branches():
    from services.aml import sar_service as ss

    prev_avail = ss._RAG_AVAILABLE
    prev_ctx = ss._rag_context
    try:
        ss._RAG_AVAILABLE = False
        assert ss.get_compliance_context("q") == ""
        ss._RAG_AVAILABLE = True
        ss._rag_context = lambda agent, query, k=3: "ctx"
        assert ss.get_compliance_context("q", agent_name="a") == "ctx"
    finally:
        ss._RAG_AVAILABLE = prev_avail
        ss._rag_context = prev_ctx


def test_sar_report_status_properties():
    from services.aml.sar_service import SARService, SARStatus

    service = SARService()
    sar = _file_draft(service)
    assert sar.requires_mlro_action is True
    assert sar.is_submittable is False
    sar.status = SARStatus.MLRO_APPROVED
    assert sar.is_submittable is True
    assert sar.requires_mlro_action is False


def test_sar_submission_error_status_code():
    from services.aml.sar_service import SARSubmissionError

    exc = SARSubmissionError("boom", status_code=503)
    assert exc.status_code == 503
    assert str(exc) == "boom"
    assert SARSubmissionError("x").status_code is None


# ── sar_service.py — MLRO gate ────────────────────────────────────────────────


def test_approve_sar_happy_and_wrong_state():
    from services.aml.sar_service import SARService, SARServiceError, SARStatus

    service = SARService()
    sar = _file_draft(service)
    approved = service.approve_sar(sar.sar_id, "mlro-7", notes="grounds ok")
    assert approved.status == SARStatus.MLRO_APPROVED
    assert approved.mlro_reviewed_by == "mlro-7"
    assert approved.mlro_notes == "grounds ok"
    assert approved.mlro_reviewed_at is not None
    # already approved → cannot approve again
    with pytest.raises(SARServiceError):
        service.approve_sar(sar.sar_id, "mlro-7")


def test_withdraw_sar_happy_and_wrong_state():
    from services.aml.sar_service import SARService, SARServiceError, SARStatus

    service = SARService()
    sar = _file_draft(service)
    withdrawn = service.withdraw_sar(sar.sar_id, "mlro-7", reason="not suspicious")
    assert withdrawn.status == SARStatus.WITHDRAWN
    assert withdrawn.mlro_notes == "not suspicious"
    # WITHDRAWN → cannot withdraw again
    with pytest.raises(SARServiceError):
        service.withdraw_sar(sar.sar_id, "mlro-7", reason="again")


def test_get_or_raise_not_found():
    from services.aml.sar_service import SARService, SARServiceError

    service = SARService()
    with pytest.raises(SARServiceError):
        service.approve_sar("does-not-exist", "mlro-7")


# ── sar_service.py — read & stats ─────────────────────────────────────────────


def test_get_sar_and_list_filtering():
    from services.aml.sar_service import SARService, SARStatus

    service = SARService()
    a = _file_draft(service, customer_id="c-a")
    b = _file_draft(service, customer_id="c-b")
    service.approve_sar(b.sar_id, "mlro-7")

    assert service.get_sar(a.sar_id).sar_id == a.sar_id
    assert service.get_sar("missing") is None

    all_sars = service.list_sars()
    assert len(all_sars) == 2
    drafts = service.list_sars(status=SARStatus.DRAFT)
    assert [s.sar_id for s in drafts] == [a.sar_id]


async def test_stats_computes_submission_rate():
    from services.aml.sar_service import SARService

    service = SARService()
    approved = _file_draft(service, customer_id="c-1")
    withdrawn = _file_draft(service, customer_id="c-2")
    _file_draft(service, customer_id="c-3")  # stays DRAFT

    service.approve_sar(approved.sar_id, "mlro-7")
    await service.submit_sar(approved.sar_id)
    service.withdraw_sar(withdrawn.sar_id, "mlro-7", reason="not suspicious")

    stats = service.stats()
    assert stats.total == 3
    assert stats.draft == 1
    assert stats.submitted == 1
    assert stats.withdrawn == 1
    assert stats.submission_rate == 50.0


# ── sar_service.py — submission (StubNCAClient) ───────────────────────────────


async def test_submit_sar_success_stub():
    from services.aml.sar_service import SARService, SARStatus

    service = SARService()
    sar = _file_draft(service)
    service.approve_sar(sar.sar_id, "mlro-7")
    submitted = await service.submit_sar(sar.sar_id)
    assert submitted.status == SARStatus.SUBMITTED
    assert submitted.nca_reference.startswith("SAR-")
    assert submitted.submitted_at is not None


async def test_submit_sar_idempotent_noop():
    from services.aml.sar_service import SARService

    service = SARService()
    sar = _file_draft(service)
    service.approve_sar(sar.sar_id, "mlro-7")
    first = await service.submit_sar(sar.sar_id)
    ref = first.nca_reference
    again = await service.submit_sar(sar.sar_id)
    assert again.nca_reference == ref


async def test_submit_sar_mlro_gate_blocks_draft():
    from services.aml.sar_service import SARService, SARServiceError

    service = SARService()
    sar = _file_draft(service)  # DRAFT, not approved
    with pytest.raises(SARServiceError):
        await service.submit_sar(sar.sar_id)


async def test_submit_sar_failure_marks_submission_failed():
    from services.aml.sar_service import SARService, SARStatus, SARSubmissionError

    class _FailingNCA:
        async def submit(self, sar):
            raise SARSubmissionError("NCA down", status_code=502)

    service = SARService(nca_client=_FailingNCA())
    sar = _file_draft(service)
    service.approve_sar(sar.sar_id, "mlro-7")
    with pytest.raises(SARSubmissionError):
        await service.submit_sar(sar.sar_id)
    failed = service.get_sar(sar.sar_id)
    assert failed.status == SARStatus.SUBMISSION_FAILED
    assert failed.errors
    # SUBMISSION_FAILED is still gated but allowed to retry.
    service._nca = __import__(
        "services.aml.sar_service", fromlist=["StubNCAClient"]
    ).StubNCAClient()
    retried = await service.submit_sar(sar.sar_id)
    assert retried.status == SARStatus.SUBMITTED


async def test_submit_sar_emits_lineage_when_recorder_wired():
    from services.aml.sar_service import SARService

    class _FakeRecorder:
        def __init__(self):
            self.records = []

        async def record(self, record):
            self.records.append(record)

    recorder = _FakeRecorder()
    service = SARService(decision_recorder=recorder)
    sar = _file_draft(service)
    service.approve_sar(sar.sar_id, "mlro-7")
    await service.submit_sar(sar.sar_id)
    assert len(recorder.records) == 1
    rec = recorder.records[0]
    assert rec.correlation_id == sar.sar_id
    assert rec.human_reviewed_by == "mlro-7"


# ── sar_service.py — StubNCAClient direct ─────────────────────────────────────


async def test_stub_nca_client_reference_format():
    from services.aml.sar_service import SARService, StubNCAClient

    service = SARService()
    sar = _file_draft(service)
    ref = await StubNCAClient().submit(sar)
    month = sar.created_at.strftime("%Y%m")
    assert ref == f"SAR-{month}-{sar.sar_id[:8].upper()}"


# ── sar_service.py — LiveNCAClient (mocked httpx) ─────────────────────────────


class _FakeResp:
    def __init__(self, status_code, json_data=None, text="", json_exc=None):
        self.status_code = status_code
        self._json = json_data
        self.text = text
        self._json_exc = json_exc

    def json(self):
        if self._json_exc is not None:
            raise self._json_exc
        return self._json


class _FakeAsyncClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.aclosed = False

    async def post(self, url, json=None, headers=None, timeout=None):
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def aclose(self):
        self.aclosed = True


def _live_client(responses, **kwargs):
    from services.aml.sar_service import LiveNCAClient

    return LiveNCAClient(
        api_key="key",
        organisation_id="org",
        client=_FakeAsyncClient(responses),
        **kwargs,
    )


def test_live_nca_missing_credentials_raises():
    from services.aml.sar_service import LiveNCAClient

    with pytest.raises(OSError):
        LiveNCAClient(api_key="", organisation_id="")


async def test_live_nca_submit_success(monkeypatch):
    from services.aml.sar_service import SARService

    service = SARService()
    sar = _file_draft(service)
    client = _live_client([_FakeResp(200, json_data={"nca_reference": "NCA-777"})])
    assert await client.submit(sar) == "NCA-777"


async def test_live_nca_submit_5xx_retries_then_succeeds():
    from services.aml.sar_service import SARService

    service = SARService()
    sar = _file_draft(service)
    client = _live_client(
        [_FakeResp(503, text="down"), _FakeResp(200, json_data={"reference": "R-1"})],
        max_retries=1,
    )
    assert await client.submit(sar) == "R-1"


async def test_live_nca_submit_5xx_exhausts():
    from services.aml.sar_service import SARService, SARSubmissionError

    service = SARService()
    sar = _file_draft(service)
    client = _live_client([_FakeResp(500, text="err")], max_retries=0)
    with pytest.raises(SARSubmissionError) as ei:
        await client.submit(sar)
    assert ei.value.status_code == 500


async def test_live_nca_submit_4xx_client_error():
    from services.aml.sar_service import SARService, SARSubmissionError

    service = SARService()
    sar = _file_draft(service)
    client = _live_client([_FakeResp(400, text="bad request body")], max_retries=1)
    with pytest.raises(SARSubmissionError) as ei:
        await client.submit(sar)
    assert ei.value.status_code == 400


async def test_live_nca_submit_transport_error_exhausts():
    from services.aml.sar_service import SARService, SARSubmissionError

    service = SARService()
    sar = _file_draft(service)
    client = _live_client([httpx.ConnectError("boom")], max_retries=0)
    with pytest.raises(SARSubmissionError):
        await client.submit(sar)


async def test_live_nca_parse_non_json_body():
    from services.aml.sar_service import SARService, SARSubmissionError

    service = SARService()
    sar = _file_draft(service)
    client = _live_client([_FakeResp(200, json_exc=ValueError("no json"))])
    with pytest.raises(SARSubmissionError):
        await client.submit(sar)


async def test_live_nca_parse_missing_reference():
    from services.aml.sar_service import SARService, SARSubmissionError

    service = SARService()
    sar = _file_draft(service)
    client = _live_client([_FakeResp(200, json_data={"unrelated": "x"})])
    with pytest.raises(SARSubmissionError):
        await client.submit(sar)


async def test_live_nca_aclose_owns_client():
    from services.aml.sar_service import LiveNCAClient

    client = LiveNCAClient(api_key="key", organisation_id="org")
    assert client._owns_client is True
    await client.aclose()


async def test_live_nca_aclose_injected_client_noop():
    fake = _FakeAsyncClient([])
    from services.aml.sar_service import LiveNCAClient

    client = LiveNCAClient(api_key="key", organisation_id="org", client=fake)
    await client.aclose()
    assert fake.aclosed is False
