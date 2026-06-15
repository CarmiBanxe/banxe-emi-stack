"""Adapter tests — the WIRED composition over the REAL L3 (no network).

Drives genuine L3 hits to prove the producer replaces default-PASS with FAIL/
ESCALATE: a real ScreeningEngine blocked-jurisdiction CONFIRMED_MATCH → FAIL,
a real TxMonitorService SAR breach → ESCALATE, and a sanctions hard-block → FAIL.
"""

from __future__ import annotations

from decimal import Decimal

from services.agents._lineage import ComplianceResult
from services.aml.tx_monitor import TxMonitorService
from services.fraud.fraud_port import (
    AppScamIndicator,
    FraudRisk,
    FraudScoringRequest,
    FraudScoringResult,
)
from services.producers.adapters import (
    AMLCheckAdapter,
    FraudCheckAdapter,
    SanctionsCheckAdapter,
)
from services.producers.ports import SanctionsIdentity
from services.sanctions_screening.models import (
    ScreeningHit,
    ScreeningReport,
    ScreeningRequest,
    ScreeningResult,
)
from services.sanctions_screening.screening_engine import ScreeningEngine
from tests.test_producers.conftest import StaticIdentity, make_request

# ── In-memory stores for the real ScreeningEngine ────────────────────────────


class _MemScreeningStore:
    def __init__(self) -> None:
        self.requests: dict[str, ScreeningRequest] = {}
        self.reports: dict[str, ScreeningReport] = {}

    def save_request(self, req: ScreeningRequest) -> None:
        self.requests[req.request_id] = req

    def get_request(self, request_id: str) -> ScreeningRequest | None:
        return self.requests.get(request_id)

    def save_report(self, report: ScreeningReport) -> None:
        self.reports[report.request_id] = report

    def get_report(self, request_id: str) -> ScreeningReport | None:
        return self.reports.get(request_id)


class _MemListStore:
    def __init__(self, entries: dict[object, list[dict]] | None = None) -> None:
        self._entries = entries or {}

    def get_list(self, source: object) -> None:
        return None

    def save_list(self, lst: object) -> None:  # pragma: no cover - unused
        pass

    def get_entries(self, source: object) -> list[dict]:
        return self._entries.get(source, [])


class _MemHitStore:
    def __init__(self) -> None:
        self.hits: list[ScreeningHit] = []

    def append(self, hit: ScreeningHit) -> None:
        self.hits.append(hit)

    def list_by_request(self, request_id: str) -> list[ScreeningHit]:
        return [h for h in self.hits if h.request_id == request_id]


def _engine(entries: dict[object, list[dict]] | None = None) -> ScreeningEngine:
    return ScreeningEngine(_MemScreeningStore(), _MemListStore(entries), _MemHitStore())


class _StubFraudScorer:
    def __init__(self, result: FraudScoringResult) -> None:
        self._result = result

    def score(self, request: FraudScoringRequest) -> FraudScoringResult:
        return self._result

    def health(self) -> bool:  # pragma: no cover - unused
        return True


def _fraud_result(**kw: object) -> FraudScoringResult:
    base: dict[str, object] = {
        "transaction_id": "corr-001",
        "risk": FraudRisk.LOW,
        "score": 10,
        "app_scam_indicator": AppScamIndicator.NONE,
        "block": False,
        "hold_for_review": False,
    }
    base.update(kw)
    return FraudScoringResult(**base)  # type: ignore[arg-type]


# ── AML adapter over the real TxMonitorService ───────────────────────────────


def test_aml_adapter_sar_breach_escalates() -> None:
    # £60k individual ≥ £50k auto-SAR → sar_required → ESCALATE (real L3).
    adapter = AMLCheckAdapter(TxMonitorService())
    outcome = adapter.check(make_request(amount=Decimal("60000")))
    assert outcome.result is ComplianceResult.ESCALATE
    assert "SAR_REQUIRED" in outcome.reason_codes


def test_aml_adapter_sanctions_hard_block_fails() -> None:
    adapter = AMLCheckAdapter(TxMonitorService())
    outcome = adapter.check(make_request(amount=Decimal("100"), is_sanctions_hit=True))
    assert outcome.result is ComplianceResult.FAIL
    assert "SANCTIONS_BLOCK" in outcome.reason_codes


def test_aml_adapter_clean_passes() -> None:
    adapter = AMLCheckAdapter(TxMonitorService())
    outcome = adapter.check(make_request(amount=Decimal("100")))
    assert outcome.result is ComplianceResult.PASS
    assert outcome.reason_codes == ()


# ── Sanctions adapter over the real ScreeningEngine ──────────────────────────


def test_sanctions_adapter_blocked_jurisdiction_fails() -> None:
    # Real engine: nationality RU is a blocked jurisdiction → CONFIRMED_MATCH → FAIL.
    adapter = SanctionsCheckAdapter(
        _engine(),
        identity=StaticIdentity(SanctionsIdentity("Acme Ltd", "organisation", "RU")),
    )
    outcome = adapter.check(make_request())
    assert outcome.result is ComplianceResult.FAIL


def test_sanctions_adapter_clear_passes() -> None:
    adapter = SanctionsCheckAdapter(
        _engine(),
        identity=StaticIdentity(SanctionsIdentity("Jane Smith", "individual", "GB")),
    )
    outcome = adapter.check(make_request())
    assert outcome.result is ComplianceResult.PASS


def test_sanctions_adapter_possible_match_escalates() -> None:
    from services.sanctions_screening.models import ListSource

    entries = {ListSource.OFSI: [{"id": "e1", "name": "Ahmad Kahn", "nationality": "GB"}]}
    adapter = SanctionsCheckAdapter(
        _engine(entries),
        identity=StaticIdentity(SanctionsIdentity("Ahmed Khan", "individual", "GB")),
    )
    outcome = adapter.check(make_request())
    # score 80 → 65 ≤ score < 85 → MEDIUM → POSSIBLE_MATCH → ESCALATE.
    assert outcome.result is ComplianceResult.ESCALATE
    assert "ofsi" in outcome.reason_codes


def test_sanctions_adapter_no_identity_is_na() -> None:
    # No PII map wired → cannot screen → N/A (never a silent PASS).
    adapter = SanctionsCheckAdapter(_engine(), identity=StaticIdentity(None))
    outcome = adapter.check(make_request())
    assert outcome.result is ComplianceResult.NA


def test_sanctions_adapter_error_escalates() -> None:
    from services.producers.adapters import _map_sanctions

    assert _map_sanctions(ScreeningResult.ERROR) is ComplianceResult.ESCALATE


# ── Fraud adapter over a stubbed FraudScoringPort ────────────────────────────


def test_fraud_adapter_block_fails() -> None:
    adapter = FraudCheckAdapter(
        _StubFraudScorer(_fraud_result(block=True, risk=FraudRisk.CRITICAL))
    )
    outcome = adapter.check(make_request())
    assert outcome.result is ComplianceResult.FAIL
    assert outcome.reason_codes == ("RISK_CRITICAL",)


def test_fraud_adapter_hold_escalates() -> None:
    adapter = FraudCheckAdapter(_StubFraudScorer(_fraud_result(hold_for_review=True)))
    assert adapter.check(make_request()).result is ComplianceResult.ESCALATE


def test_fraud_adapter_app_scam_escalates() -> None:
    adapter = FraudCheckAdapter(
        _StubFraudScorer(_fraud_result(app_scam_indicator=AppScamIndicator.ROMANCE_SCAM))
    )
    assert adapter.check(make_request()).result is ComplianceResult.ESCALATE


def test_fraud_adapter_high_risk_escalates() -> None:
    adapter = FraudCheckAdapter(_StubFraudScorer(_fraud_result(risk=FraudRisk.HIGH, score=75)))
    assert adapter.check(make_request()).result is ComplianceResult.ESCALATE


def test_fraud_adapter_low_risk_passes() -> None:
    adapter = FraudCheckAdapter(_StubFraudScorer(_fraud_result()))
    assert adapter.check(make_request(amount=Decimal("0"))).result is ComplianceResult.PASS
