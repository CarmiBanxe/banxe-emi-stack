"""
tests/test_sumsub_http.py — Unit tests for SumsubHttpAdapter + SumsubHttpStub.

All HTTP is mocked via an injected httpx.Client — no real SumSub API calls.
Covers: HMAC signing, status mapping, success + error/fail-closed branches on the
adapter, and NotImplementedError on every stub method.

Canon: ADR-025 §15-16 + PORT-CONTRACTS-FREEZE-2026-05-08 + [IL-KYC-PROD-01]
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import httpx
import pytest

from services.compliance.legacy.legacy_sumsub_adapter import SumSubApplicationError
from services.compliance.production.sumsub_http_adapter import (
    SumsubHttpAdapter,
    _map_status,
)
from services.compliance.production.sumsub_http_stub import SumsubHttpStub
from services.kyc.kyc_port import (
    KYCStatus,
    KYCType,
    KYCWorkflowRequest,
    RejectionReason,
)

# ── Fixtures / helpers ────────────────────────────────────────────────────────

_APPLICANT = {
    "id": "app-001",
    "externalUserId": "cust-001",
    "createdAt": "2026-05-09 10:00:00",
    "review": {"reviewStatus": "init"},
}


def _resp(json_data: object) -> MagicMock:
    """A 2xx-style response mock: raise_for_status is a no-op."""
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


def _error_resp(status_code: int) -> MagicMock:
    """A response mock whose raise_for_status raises HTTPStatusError."""
    req = httpx.Request("GET", "https://api.sumsub.com/x")
    http_resp = httpx.Response(status_code, request=req)
    resp = MagicMock()
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        f"{status_code}", request=req, response=http_resp
    )
    return resp


def _client(responses: list[object]) -> MagicMock:
    """A mock httpx.Client whose .request yields the given responses/exceptions."""
    client = MagicMock(spec=httpx.Client)
    client.request.side_effect = responses
    return client


@pytest.fixture()
def env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUMSUB_APP_TOKEN", "test_app_token_0000000000")
    monkeypatch.setenv("SUMSUB_SECRET_KEY", "test_secret_key_000000000")
    monkeypatch.setenv("SUMSUB_BASE_URL", "https://api.sumsub.com")


def _request(**overrides: object) -> KYCWorkflowRequest:
    base: dict[str, object] = {
        "customer_id": "cust-001",
        "kyc_type": KYCType.INDIVIDUAL,
        "first_name": "Ada",
        "last_name": "Lovelace",
        "date_of_birth": "1990-01-01",
        "nationality": "GB",
        "country_of_residence": "GB",
        "expected_transaction_volume": Decimal("500.00"),
    }
    base.update(overrides)
    return KYCWorkflowRequest(**base)  # type: ignore[arg-type]


# ── _map_status: all branches (lines 56-67) ───────────────────────────────────


@pytest.mark.parametrize(
    ("review", "expected"),
    [
        ({"reviewStatus": "init"}, KYCStatus.PENDING),
        ({"reviewStatus": "pending"}, KYCStatus.DOCUMENT_REVIEW),
        ({"reviewStatus": "queued"}, KYCStatus.RISK_ASSESSMENT),
        ({"reviewStatus": "onHold"}, KYCStatus.EDD_REQUIRED),
        ({"reviewStatus": "completed", "reviewAnswer": "GREEN"}, KYCStatus.APPROVED),
        ({"reviewStatus": "completed", "reviewAnswer": "RED"}, KYCStatus.REJECTED),
        ({"reviewStatus": "somethingElse"}, KYCStatus.PENDING),
        ({}, KYCStatus.PENDING),
    ],
)
def test_map_status(review: dict[str, object], expected: KYCStatus) -> None:
    assert _map_status(review) == expected


# ── create_workflow ───────────────────────────────────────────────────────────


def test_create_workflow_individual_success(env_vars: None) -> None:
    client = _client([_resp(_APPLICANT)])
    adapter = SumsubHttpAdapter(http_client=client)

    result = adapter.create_workflow(_request())

    assert result.workflow_id == "app-001"
    assert result.customer_id == "cust-001"
    assert result.status == KYCStatus.PENDING
    assert result.kyc_type == KYCType.INDIVIDUAL
    assert result.edd_required is False
    # one audit record emitted (CREATED)
    assert len(adapter.collect_audit_records()) == 1
    # HMAC headers present on the outgoing request
    _, kwargs = client.request.call_args
    headers = kwargs["headers"]
    assert headers["X-App-Token"] == "test_app_token_0000000000"
    assert "X-App-Access-Sig" in headers
    assert "X-App-Access-Ts" in headers


def test_create_workflow_business_builds_company_info(env_vars: None) -> None:
    applicant = {**_APPLICANT, "companyInfo": {"companyName": "ACME"}}
    client = _client([_resp(applicant)])
    adapter = SumsubHttpAdapter(http_client=client)

    result = adapter.create_workflow(
        _request(
            kyc_type=KYCType.BUSINESS,
            business_name="ACME Ltd",
            registration_number="12345678",
            expected_transaction_volume=Decimal("60000.00"),
        )
    )

    assert result.kyc_type == KYCType.BUSINESS
    assert result.edd_required is True  # >£50k business threshold
    _, kwargs = client.request.call_args
    body = kwargs["content"].decode()
    assert "companyInfo" in body
    assert "ACME Ltd" in body
    assert "12345678" in body


def test_create_workflow_blocked_jurisdiction_raises(env_vars: None) -> None:
    client = _client([])  # no HTTP call should happen
    adapter = SumsubHttpAdapter(http_client=client)

    with pytest.raises(SumSubApplicationError):
        adapter.create_workflow(_request(nationality="RU"))
    client.request.assert_not_called()


# ── get_workflow ──────────────────────────────────────────────────────────────


def test_get_workflow_success(env_vars: None) -> None:
    client = _client([_resp(_APPLICANT)])
    adapter = SumsubHttpAdapter(http_client=client)

    result = adapter.get_workflow("app-001")

    assert result is not None
    assert result.workflow_id == "app-001"


def test_get_workflow_404_returns_none(env_vars: None) -> None:
    client = _client([_error_resp(404)])
    adapter = SumsubHttpAdapter(http_client=client)

    assert adapter.get_workflow("missing") is None


def test_get_workflow_500_reraises(env_vars: None) -> None:
    client = _client([_error_resp(500)])
    adapter = SumsubHttpAdapter(http_client=client)

    with pytest.raises(httpx.HTTPStatusError):
        adapter.get_workflow("boom")


# ── submit_documents / approve_edd / reject_workflow ──────────────────────────


def test_submit_documents(env_vars: None) -> None:
    doc_review = {**_APPLICANT, "review": {"reviewStatus": "pending"}}
    # POST status/pending, then GET applicant
    client = _client([_resp({}), _resp(doc_review)])
    adapter = SumsubHttpAdapter(http_client=client)

    result = adapter.submit_documents("app-001", ["doc-1"])

    assert result.status == KYCStatus.DOCUMENT_REVIEW
    assert client.request.call_count == 2
    audit = adapter.collect_audit_records()
    assert audit[-1].status_to == KYCStatus.DOCUMENT_REVIEW


def test_approve_edd(env_vars: None) -> None:
    approved = {
        **_APPLICANT,
        "review": {"reviewStatus": "completed", "reviewAnswer": "GREEN"},
    }
    client = _client([_resp({}), _resp(approved)])
    adapter = SumsubHttpAdapter(http_client=client)

    result = adapter.approve_edd("app-001", "mlro-42")

    assert result.status == KYCStatus.APPROVED
    assert result.mlro_sign_off is True
    assert client.request.call_count == 2


def test_reject_workflow(env_vars: None) -> None:
    rejected = {
        **_APPLICANT,
        "review": {"reviewStatus": "completed", "reviewAnswer": "RED"},
    }
    client = _client([_resp({}), _resp(rejected)])
    adapter = SumsubHttpAdapter(http_client=client)

    result = adapter.reject_workflow("app-001", RejectionReason.SANCTIONS_HIT)

    assert result.status == KYCStatus.REJECTED
    assert result.rejection_reason == RejectionReason.SANCTIONS_HIT
    # rejectLabels body carried the reason
    first_post = client.request.call_args_list[0]
    assert "SANCTIONS_HIT" in first_post.kwargs["content"].decode()


# ── health / close / audit ────────────────────────────────────────────────────


def test_health_true(env_vars: None) -> None:
    client = _client([_resp({})])
    adapter = SumsubHttpAdapter(http_client=client)

    assert adapter.health() is True


def test_health_false_on_exception(env_vars: None) -> None:
    client = _client([httpx.ConnectError("down")])
    adapter = SumsubHttpAdapter(http_client=client)

    assert adapter.health() is False


def test_close_delegates_to_client(env_vars: None) -> None:
    client = _client([])
    adapter = SumsubHttpAdapter(http_client=client)

    adapter.close()

    client.close.assert_called_once()


def test_collect_audit_records_returns_copy(env_vars: None) -> None:
    client = _client([_resp(_APPLICANT)])
    adapter = SumsubHttpAdapter(http_client=client)
    adapter.create_workflow(_request())

    records = adapter.collect_audit_records()
    records.clear()  # mutating the copy must not affect internal log
    assert len(adapter.collect_audit_records()) == 1


def test_default_http_client_constructed(env_vars: None) -> None:
    # No injected client → adapter builds its own httpx.Client (no network here).
    adapter = SumsubHttpAdapter()
    assert isinstance(adapter._http, httpx.Client)
    adapter.close()


# ── SumsubHttpStub: every method raises NotImplementedError ────────────────────


def test_stub_all_methods_not_implemented() -> None:
    stub = SumsubHttpStub()
    with pytest.raises(NotImplementedError):
        stub.create_workflow(_request())
    with pytest.raises(NotImplementedError):
        stub.get_workflow("wf-1")
    with pytest.raises(NotImplementedError):
        stub.submit_documents("wf-1", ["doc-1"])
    with pytest.raises(NotImplementedError):
        stub.approve_edd("wf-1", "mlro-1")
    with pytest.raises(NotImplementedError):
        stub.reject_workflow("wf-1", RejectionReason.SANCTIONS_HIT)
    with pytest.raises(NotImplementedError):
        stub.health()
