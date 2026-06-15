"""
tests/test_sumsub_http_adapter.py — Unit tests for SumsubHttpAdapter.

All HTTP calls are mocked — no real SumSub API calls.
Integration tests (real SumSub sandbox) are a separate CI job requiring
SUMSUB_APP_TOKEN / SUMSUB_SECRET_KEY secrets.

Tests: 18
Canon: ADR-025 §15-16 + PORT-CONTRACTS-FREEZE-2026-05-08 + [IL-KYC-PROD-01]
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import httpx
import pytest

from services.compliance.legacy.legacy_sumsub_adapter import SumSubApplicationError
from services.kyc.kyc_port import (
    KYCStatus,
    KYCType,
    KYCWorkflowRequest,
    KYCWorkflowResult,
    RejectionReason,
)

# ── Shared fixtures ───────────────────────────────────────────────────────────

_APPLICANT_PENDING = {
    "id": "app-001",
    "externalUserId": "cust-001",
    "createdAt": "2026-05-09 10:00:00",
    "review": {"reviewStatus": "init"},
}

_APPLICANT_DOC_REVIEW = {**_APPLICANT_PENDING, "review": {"reviewStatus": "pending"}}
_APPLICANT_APPROVED = {
    **_APPLICANT_PENDING,
    "review": {"reviewStatus": "completed", "reviewAnswer": "GREEN"},
}
_APPLICANT_REJECTED = {
    **_APPLICANT_PENDING,
    "review": {"reviewStatus": "completed", "reviewAnswer": "RED"},
}


def _make_resp(json_data: object, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    return resp


@pytest.fixture()
def env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUMSUB_APP_TOKEN", "test_app_token_0000000000")
    monkeypatch.setenv("SUMSUB_SECRET_KEY", "test_secret_key_000000000")
    monkeypatch.setenv("SUMSUB_BASE_URL", "https://api.sumsub.com")


@pytest.fixture()
def mock_http() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def adapter(env_vars: None, mock_http: MagicMock) -> object:
    with patch(
        "services.compliance.production.sumsub_http_adapter.httpx.Client",
        return_value=mock_http,
    ):
        from services.compliance.production.sumsub_http_adapter import SumsubHttpAdapter

        return SumsubHttpAdapter(sandbox=True)


def _make_request(
    kyc_type: KYCType = KYCType.INDIVIDUAL, volume: str = "1000"
) -> KYCWorkflowRequest:
    return KYCWorkflowRequest(
        customer_id="cust-001",
        kyc_type=kyc_type,
        first_name="Alice",
        last_name="Smith",
        date_of_birth="1990-01-01",
        nationality="GB",
        country_of_residence="GB",
        expected_transaction_volume=Decimal(volume),
    )


# ── Protocol structure ────────────────────────────────────────────────────────


def test_adapter_has_all_port_methods(adapter: object) -> None:
    for method in (
        "create_workflow",
        "get_workflow",
        "submit_documents",
        "approve_edd",
        "reject_workflow",
        "health",
    ):
        assert callable(getattr(adapter, method, None)), f"Missing port method: {method}"


# ── create_workflow ───────────────────────────────────────────────────────────


def test_create_workflow_sends_post_to_applicants(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.return_value = _make_resp(_APPLICANT_PENDING)

    adapter.create_workflow(_make_request())  # type: ignore[attr-defined]

    call_args = mock_http.request.call_args
    assert call_args[0][0] == "POST"
    assert "/resources/applicants" in call_args[0][1]


def test_create_workflow_returns_kyc_workflow_result(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.return_value = _make_resp(_APPLICANT_PENDING)

    result = adapter.create_workflow(_make_request())  # type: ignore[attr-defined]

    assert isinstance(result, KYCWorkflowResult)
    assert result.workflow_id == "app-001"
    assert result.customer_id == "cust-001"
    assert result.status == KYCStatus.PENDING


def test_create_workflow_blocks_ru_nationality(adapter: object) -> None:
    req = KYCWorkflowRequest(
        customer_id="cust-002",
        kyc_type=KYCType.INDIVIDUAL,
        first_name="Ivan",
        last_name="Petrov",
        date_of_birth="1985-06-15",
        nationality="RU",
        country_of_residence="GB",
        expected_transaction_volume=Decimal("500"),
    )
    with pytest.raises(SumSubApplicationError, match="Blocked jurisdiction"):
        adapter.create_workflow(req)  # type: ignore[attr-defined]


def test_create_workflow_blocks_by_country_of_residence(adapter: object) -> None:
    req = _make_request()
    object.__setattr__(req, "country_of_residence", "BY")
    with pytest.raises(SumSubApplicationError, match="Blocked jurisdiction"):
        adapter.create_workflow(req)  # type: ignore[attr-defined]


def test_create_workflow_sets_edd_flag_above_10k_individual(
    adapter: object, mock_http: MagicMock
) -> None:
    mock_http.request.return_value = _make_resp(_APPLICANT_PENDING)

    result = adapter.create_workflow(_make_request(volume="10000"))  # type: ignore[attr-defined]

    assert result.edd_required is True  # type: ignore[attr-defined]


def test_create_workflow_no_edd_below_threshold(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.return_value = _make_resp(_APPLICANT_PENDING)

    result = adapter.create_workflow(_make_request(volume="999"))  # type: ignore[attr-defined]

    assert result.edd_required is False  # type: ignore[attr-defined]


def test_create_workflow_emits_audit_record(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.return_value = _make_resp(_APPLICANT_PENDING)

    adapter.create_workflow(_make_request())  # type: ignore[attr-defined]
    records = adapter.collect_audit_records()  # type: ignore[attr-defined]

    assert len(records) == 1
    assert records[0].event_type == "CREATED"
    assert records[0].status_from is None
    assert records[0].status_to == KYCStatus.PENDING


# ── get_workflow ──────────────────────────────────────────────────────────────


def test_get_workflow_calls_applicants_get(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.return_value = _make_resp(_APPLICANT_PENDING)

    adapter.get_workflow("app-001")  # type: ignore[attr-defined]

    call_args = mock_http.request.call_args
    assert call_args[0][0] == "GET"
    assert "app-001" in call_args[0][1]


def test_get_workflow_returns_none_on_404(adapter: object, mock_http: MagicMock) -> None:
    resp_404 = _make_resp({}, status_code=404)
    resp_404.raise_for_status.side_effect = httpx.HTTPStatusError(
        "not found", request=MagicMock(), response=resp_404
    )
    mock_http.request.return_value = resp_404

    result = adapter.get_workflow("nonexistent-id")  # type: ignore[attr-defined]

    assert result is None


# ── submit_documents ──────────────────────────────────────────────────────────


def test_submit_documents_calls_pending_then_get(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.side_effect = [
        _make_resp({"ok": 1}),
        _make_resp(_APPLICANT_DOC_REVIEW),
    ]

    adapter.submit_documents("app-001", ["doc-1", "doc-2"])  # type: ignore[attr-defined]

    assert mock_http.request.call_count == 2
    first_call = mock_http.request.call_args_list[0]
    assert first_call[0][0] == "POST"
    assert "status/pending" in first_call[0][1]


def test_submit_documents_returns_document_review_status(
    adapter: object, mock_http: MagicMock
) -> None:
    mock_http.request.side_effect = [
        _make_resp({"ok": 1}),
        _make_resp(_APPLICANT_DOC_REVIEW),
    ]

    result = adapter.submit_documents("app-001", ["doc-1"])  # type: ignore[attr-defined]

    assert isinstance(result, KYCWorkflowResult)
    assert result.status == KYCStatus.DOCUMENT_REVIEW


# ── approve_edd ───────────────────────────────────────────────────────────────


def test_approve_edd_calls_approve_then_get(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.side_effect = [
        _make_resp({"ok": 1}),
        _make_resp(_APPLICANT_APPROVED),
    ]

    result = adapter.approve_edd("app-001", "mlro-user-42")  # type: ignore[attr-defined]

    assert mock_http.request.call_count == 2
    first_call = mock_http.request.call_args_list[0]
    assert "status/approve" in first_call[0][1]
    assert result.status == KYCStatus.APPROVED  # type: ignore[attr-defined]
    assert result.mlro_sign_off is True  # type: ignore[attr-defined]


# ── reject_workflow ───────────────────────────────────────────────────────────


def test_reject_workflow_calls_reject_then_get(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.side_effect = [
        _make_resp({"ok": 1}),
        _make_resp(_APPLICANT_REJECTED),
    ]

    result = adapter.reject_workflow("app-001", RejectionReason.SANCTIONS_HIT)  # type: ignore[attr-defined]

    first_call = mock_http.request.call_args_list[0]
    assert "status/reject" in first_call[0][1]
    assert result.rejection_reason == RejectionReason.SANCTIONS_HIT  # type: ignore[attr-defined]


# ── health ────────────────────────────────────────────────────────────────────


def test_health_returns_true_on_200(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.return_value = _make_resp({"status": "GREEN"})
    assert adapter.health() is True  # type: ignore[attr-defined]


def test_health_returns_false_on_exception(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.side_effect = httpx.ConnectError("unreachable")
    assert adapter.health() is False  # type: ignore[attr-defined]


# ── HMAC signing ──────────────────────────────────────────────────────────────


def test_sign_includes_required_hmac_headers(adapter: object, mock_http: MagicMock) -> None:
    mock_http.request.return_value = _make_resp(_APPLICANT_PENDING)

    adapter.get_workflow("app-001")  # type: ignore[attr-defined]

    headers = mock_http.request.call_args[1]["headers"]
    assert "X-App-Token" in headers
    assert "X-App-Access-Ts" in headers
    assert "X-App-Access-Sig" in headers
    assert len(headers["X-App-Access-Sig"]) == 64  # SHA-256 hex digest


# ── close ─────────────────────────────────────────────────────────────────────


def test_close_calls_http_close(adapter: object, mock_http: MagicMock) -> None:
    adapter.close()  # type: ignore[attr-defined]
    mock_http.close.assert_called_once()
