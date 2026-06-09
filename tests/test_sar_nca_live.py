"""
tests/test_sar_nca_live.py — LiveNCAClient + SAR→NCA submission tests.
S6.1 | POCA 2002 s.330 | banxe-emi-stack

Covers the live NCA SAROnline submission path (LiveNCAClient), the SARService
state-machine guards around it, and the R-SEC proof that SAR-body PII never
reaches the ADR-046 decision lineage.

Network is mocked two ways:
  - httpx.MockTransport  — behavioural tests (a real async client + transport;
    a missing ``await`` would yield a coroutine, not a Response, and fail).
  - strict AsyncMock(spec=httpx.AsyncClient) — proves ``.post`` is AWAITED
    exactly once (the adapter-bug-class await discipline).
"""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
import json
from unittest.mock import AsyncMock

import httpx
import pytest

import api.routers.reporting as reporting
from services.agents._lineage import AgentDecisionRecord, DecisionRecorder
from services.aml.sar_service import (
    LiveNCAClient,
    NCAClient,
    SARReason,
    SARReport,
    SARService,
    SARServiceError,
    SARStatus,
    SARSubmissionError,
    StubNCAClient,
)

# ── Fixtures / helpers ─────────────────────────────────────────────────────────


def _make_draft(svc: SARService) -> SARReport:
    return svc.file_sar(
        transaction_id="tx-PII-999",
        customer_id="cust-PII-001",
        entity_type="INDIVIDUAL",
        amount=Decimal("12500"),
        currency="GBP",
        sar_reasons=[SARReason.VELOCITY_BREACH, SARReason.STRUCTURING],
        aml_flags=["VELOCITY_30D"],
        fraud_score=72,
    )


def _approved(svc: SARService) -> SARReport:
    sar = _make_draft(svc)
    svc.approve_sar(sar_id=sar.sar_id, mlro_id="mlro-001", notes="clear ML indicators")
    return sar


def _live_with(handler, **kwargs) -> LiveNCAClient:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return LiveNCAClient(api_key="k-test", organisation_id="org-test", client=client, **kwargs)


def _ok(reference: str = "NCA-REF-123"):
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"reference": reference})

    return handler


class _CapturingRecorder(DecisionRecorder):
    """Captures every emitted AgentDecisionRecord for inspection."""

    def __init__(self) -> None:
        self.records: list[AgentDecisionRecord] = []

    async def record(self, record: AgentDecisionRecord) -> None:
        self.records.append(record)


# ── LiveNCAClient construction / cutover ───────────────────────────────────────


class TestLiveNCAClientConstruction:
    def test_satisfies_nca_client_protocol(self) -> None:
        client = _live_with(_ok())
        assert isinstance(client, NCAClient)

    def test_missing_api_key_raises(self) -> None:
        with pytest.raises(OSError, match="NCA_SAR_API_KEY"):
            LiveNCAClient(api_key="", organisation_id="org")

    def test_missing_org_id_raises(self) -> None:
        with pytest.raises(OSError, match="NCA_ORGANISATION_ID"):
            LiveNCAClient(api_key="k", organisation_id="")

    def test_base_url_defaults_to_test_sandbox(self) -> None:
        client = _live_with(_ok())
        assert "test" in client._base_url  # TEST/sandbox default for acceptance (a)

    def test_base_url_override(self) -> None:
        client = LiveNCAClient(
            api_key="k", organisation_id="o", base_url="https://prod.example/", client=None
        )
        assert client._base_url == "https://prod.example"


class TestCutover:
    """_build_nca_client(): live IFF both creds present, else stub (offline)."""

    def test_stub_when_no_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NCA_SAR_API_KEY", raising=False)
        monkeypatch.delenv("NCA_ORGANISATION_ID", raising=False)
        assert isinstance(reporting._build_nca_client(), StubNCAClient)

    def test_stub_when_only_one_credential(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NCA_SAR_API_KEY", "k")
        monkeypatch.delenv("NCA_ORGANISATION_ID", raising=False)
        assert isinstance(reporting._build_nca_client(), StubNCAClient)

    def test_live_when_both_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NCA_SAR_API_KEY", "k")
        monkeypatch.setenv("NCA_ORGANISATION_ID", "org")
        assert isinstance(reporting._build_nca_client(), LiveNCAClient)


# ── LiveNCAClient.submit — happy path / await discipline ───────────────────────


class TestLiveSubmit:
    async def test_2xx_returns_reference(self) -> None:
        client = _live_with(_ok("NCA-OK-1"))
        svc = SARService(nca_client=client)
        sar = _approved(svc)
        ref = await client.submit(sar)
        assert ref == "NCA-OK-1"

    async def test_await_discipline_strict_asyncmock(self) -> None:
        """A missing ``await`` on .post would yield a coroutine and blow up."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = httpx.Response(200, json={"reference": "NCA-AM-1"})
        client = LiveNCAClient(api_key="k", organisation_id="o", client=mock_client)
        sar = _approved(SARService())
        ref = await client.submit(sar)
        assert ref == "NCA-AM-1"
        mock_client.post.assert_awaited_once()  # proves the await happened

    async def test_payload_and_headers(self) -> None:
        seen: dict = {}

        def handler(req: httpx.Request) -> httpx.Response:
            seen["headers"] = dict(req.headers)
            seen["body"] = json.loads(req.content)
            seen["url"] = str(req.url)
            return httpx.Response(200, json={"reference": "R"})

        client = _live_with(handler)
        sar = _approved(SARService())
        await client.submit(sar)
        assert seen["url"].endswith("/v1/sar/submit")
        assert seen["headers"]["authorization"] == "Bearer k-test"
        assert seen["headers"]["x-organisation-id"] == "org-test"
        # Submission lock: idempotency key == SAR id (safe retry).
        assert seen["headers"]["idempotency-key"] == sar.sar_id
        # Money is a string (Decimal), never a float.
        assert seen["body"]["amount"] == "12500"
        assert isinstance(seen["body"]["amount"], str)
        assert seen["body"]["sarId"] == sar.sar_id

    async def test_reference_alternate_key(self) -> None:
        def handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"ncaReference": "ALT-1"})

        client = _live_with(handler)
        assert await client.submit(_approved(SARService())) == "ALT-1"


# ── LiveNCAClient.submit — error mapping / retry ───────────────────────────────


class TestLiveSubmitErrors:
    async def test_4xx_raises_no_retry(self) -> None:
        calls = {"n": 0}

        def handler(_req: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(400, text="bad request body")

        client = _live_with(handler, max_retries=3)
        with pytest.raises(SARSubmissionError) as ei:
            await client.submit(_approved(SARService()))
        assert ei.value.status_code == 400
        assert "bad request body" in str(ei.value)  # _safe_snippet
        assert calls["n"] == 1  # 4xx is NOT retried

    async def test_5xx_retried_then_raises(self) -> None:
        calls = {"n": 0}

        def handler(_req: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(500)

        client = _live_with(handler, max_retries=2)
        with pytest.raises(SARSubmissionError) as ei:
            await client.submit(_approved(SARService()))
        assert ei.value.status_code == 500
        assert calls["n"] == 3  # initial + 2 retries

    async def test_5xx_then_2xx_succeeds(self) -> None:
        seq = [503, 200]

        def handler(_req: httpx.Request) -> httpx.Response:
            code = seq.pop(0)
            if code == 200:
                return httpx.Response(200, json={"reference": "RECOVERED"})
            return httpx.Response(code)

        client = _live_with(handler, max_retries=2)
        assert await client.submit(_approved(SARService())) == "RECOVERED"

    async def test_transport_error_raises(self) -> None:
        def handler(_req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("dns failure")

        client = _live_with(handler, max_retries=1)
        with pytest.raises(SARSubmissionError, match="transport error"):
            await client.submit(_approved(SARService()))

    async def test_2xx_without_reference_raises(self) -> None:
        def handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"status": "ok"})

        client = _live_with(handler)
        with pytest.raises(SARSubmissionError, match="no reference"):
            await client.submit(_approved(SARService()))

    async def test_2xx_non_json_raises(self) -> None:
        def handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="not json", headers={"content-type": "text/plain"})

        client = _live_with(handler)
        with pytest.raises(SARSubmissionError, match="non-JSON"):
            await client.submit(_approved(SARService()))


# ── aclose ─────────────────────────────────────────────────────────────────────


class TestAclose:
    async def test_aclose_owned_client(self) -> None:
        client = LiveNCAClient(api_key="k", organisation_id="o")  # owns its client
        await client.aclose()
        assert client._client.is_closed

    async def test_aclose_injected_client_not_closed(self) -> None:
        injected = httpx.AsyncClient()
        client = LiveNCAClient(api_key="k", organisation_id="o", client=injected)
        await client.aclose()  # must NOT close a client it does not own
        assert not injected.is_closed
        await injected.aclose()


# ── SARService submission guards (with live client) ────────────────────────────


class TestServiceSubmissionGuards:
    async def test_submit_sets_reference_and_status(self) -> None:
        svc = SARService(nca_client=_live_with(_ok("NCA-S-1")))
        sar = _approved(svc)
        result = await svc.submit_sar(sar.sar_id)
        assert result.status == SARStatus.SUBMITTED
        assert result.nca_reference == "NCA-S-1"
        assert result.submitted_at is not None

    async def test_refuses_non_mlro_approved(self) -> None:
        svc = SARService(nca_client=_live_with(_ok()))
        draft = _make_draft(svc)  # DRAFT, not approved
        with pytest.raises(SARServiceError, match="must be MLRO_APPROVED"):
            await svc.submit_sar(draft.sar_id)

    async def test_double_submit_is_noop(self) -> None:
        calls = {"n": 0}

        def handler(_req: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, json={"reference": "ONCE"})

        svc = SARService(nca_client=_live_with(handler))
        sar = _approved(svc)
        first = await svc.submit_sar(sar.sar_id)
        second = await svc.submit_sar(sar.sar_id)  # idempotent no-op
        assert first.nca_reference == second.nca_reference == "ONCE"
        assert calls["n"] == 1  # NCA hit exactly once

    async def test_submission_failure_sets_failed_status_and_raises(self) -> None:
        svc = SARService(nca_client=_live_with(lambda _r: httpx.Response(400, text="rejected")))
        sar = _approved(svc)
        with pytest.raises(SARSubmissionError):
            await svc.submit_sar(sar.sar_id)
        failed = svc.get_sar(sar.sar_id)
        assert failed is not None
        assert failed.status == SARStatus.SUBMISSION_FAILED
        assert failed.errors  # error recorded, not swallowed

    async def test_retry_after_failure_succeeds(self) -> None:
        seq = [httpx.Response(500), httpx.Response(200, json={"reference": "RETRY-OK"})]
        svc = SARService(nca_client=_live_with(lambda _r: seq.pop(0), max_retries=0))
        sar = _approved(svc)
        with pytest.raises(SARSubmissionError):
            await svc.submit_sar(sar.sar_id)  # first attempt fails → SUBMISSION_FAILED
        result = await svc.submit_sar(sar.sar_id)  # retry from SUBMISSION_FAILED
        assert result.status == SARStatus.SUBMITTED
        assert result.nca_reference == "RETRY-OK"


# ── R-SEC: SAR-body PII never reaches the ADR-046 lineage ──────────────────────


class TestLineagePIISafety:
    async def test_submitted_emits_lineage_without_pii(self) -> None:
        recorder = _CapturingRecorder()
        svc = SARService(nca_client=StubNCAClient(), decision_recorder=recorder)
        sar = _approved(svc)
        await svc.submit_sar(sar.sar_id)

        assert len(recorder.records) == 1
        record = recorder.records[0]
        blob = str(asdict(record))

        # Safe identifiers ARE present.
        assert sar.sar_id in blob
        assert sar.nca_reference is not None
        assert sar.nca_reference in blob
        assert "SUBMITTED" in blob

        # SAR-body PII is NEVER present.
        assert sar.customer_id not in blob  # cust-PII-001
        assert sar.transaction_id not in blob  # tx-PII-999
        assert str(sar.amount) not in blob  # 12500
        for reason in sar.sar_reasons:
            assert reason.value not in blob
        for flag in sar.aml_flags:
            assert flag not in blob

    async def test_no_recorder_means_no_emission(self) -> None:
        svc = SARService(nca_client=StubNCAClient())  # no recorder
        sar = _approved(svc)
        result = await svc.submit_sar(sar.sar_id)  # must not raise
        assert result.status == SARStatus.SUBMITTED


# ── API endpoint: NCA failure surfaces as 502 (no silent swallow) ──────────────


class TestSubmitEndpointErrorMapping:
    def test_nca_failure_maps_to_502(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from fastapi.testclient import TestClient

        from api.main import app

        failing = SARService(nca_client=_live_with(lambda _r: httpx.Response(503), max_retries=0))
        sar = _approved(failing)
        monkeypatch.setattr(reporting, "_get_sar_service", lambda: failing)
        with TestClient(app) as client:
            res = client.post(f"/v1/reporting/sar/{sar.sar_id}/submit")
        assert res.status_code == 502
        assert "NCA SAROnline submission failed" in res.json()["detail"]
