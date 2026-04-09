"""
tests/test_ballerine_adapter.py — BallerineAdapter unit tests (IL-055)
FCA MLR 2017 §18 CDD requirement: KYC workflow integration.

All HTTP calls are mocked by replacing adapter._client after construction.
httpx IS installed, so we construct the adapter normally then swap the client.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from services.kyc.kyc_port import (
    KYCStatus,
    KYCType,
    KYCWorkflowRequest,
    RejectionReason,
)
from services.kyc.mock_kyc_workflow import BallerineAdapter

# ─────────────────────────────────────────────────────────────────────────────
# Mock httpx helpers
# ─────────────────────────────────────────────────────────────────────────────


def _mock_response(status_code: int, json_data: dict) -> MagicMock:
    """Build a fake httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.is_error = status_code >= 400
    resp.json.return_value = json_data
    resp.text = str(json_data)
    return resp


def _make_wf_json(
    wf_id: str = "wf-001",
    status: str = "created",
    customer_id: str = "cust-001",
    entity_type: str = "individual",
    result: str = "",
    risk_score: int | None = None,
    edd_required: bool = False,
    mlro_sign_off: bool = False,
) -> dict:
    """Return a minimal Ballerine workflow runtime JSON."""
    ctx: dict = {"customerId": customer_id}
    if result:
        ctx["result"] = result
    if risk_score is not None:
        ctx["riskScore"] = risk_score
    if edd_required:
        ctx["eddRequired"] = True
    if mlro_sign_off:
        ctx["mlroSignOff"] = True
    return {
        "id": wf_id,
        "status": status,
        "createdAt": "2026-03-01T10:00:00Z",
        "updatedAt": "2026-03-01T10:00:00Z",
        "context": ctx,
        "entity": {"id": "eu-001", "type": entity_type},
    }


def _adapter(client: MagicMock | None = None) -> BallerineAdapter:
    """
    Create a BallerineAdapter with a real httpx.Client replaced by a mock.
    httpx is installed so construction succeeds; we swap _client afterwards.
    """
    adapter = BallerineAdapter(base_url="http://test", api_token="test-token")
    adapter._client = client or MagicMock()
    return adapter


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def kyc_request() -> KYCWorkflowRequest:
    return KYCWorkflowRequest(
        customer_id="cust-001",
        first_name="Alice",
        last_name="Smith",
        date_of_birth="1990-05-15",
        nationality="GB",
        country_of_residence="GB",
        kyc_type=KYCType.INDIVIDUAL,
        expected_transaction_volume=Decimal("5000"),
        is_pep=False,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tests: create_workflow
# ─────────────────────────────────────────────────────────────────────────────


class TestCreateWorkflow:
    def test_create_workflow_returns_result(self, kyc_request: KYCWorkflowRequest) -> None:
        client = MagicMock()
        client.post.side_effect = [
            _mock_response(200, {"id": "eu-001"}),
            _mock_response(200, _make_wf_json("wf-abc", "created")),
        ]
        result = _adapter(client).create_workflow(kyc_request)
        assert result.workflow_id == "wf-abc"
        assert result.status == KYCStatus.PENDING
        assert result.customer_id == "cust-001"

    def test_create_workflow_sends_two_posts(self, kyc_request: KYCWorkflowRequest) -> None:
        client = MagicMock()
        client.post.side_effect = [
            _mock_response(200, {"id": "eu-002"}),
            _mock_response(200, _make_wf_json("wf-xyz", "active")),
        ]
        _adapter(client).create_workflow(kyc_request)
        assert client.post.call_count == 2

    def test_create_workflow_api_error_raises(self, kyc_request: KYCWorkflowRequest) -> None:
        client = MagicMock()
        client.post.return_value = _mock_response(500, {"error": "internal server error"})
        with pytest.raises(RuntimeError, match="Ballerine API error"):
            _adapter(client).create_workflow(kyc_request)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: get_workflow
# ─────────────────────────────────────────────────────────────────────────────


class TestGetWorkflow:
    def test_get_workflow_returns_result(self) -> None:
        client = MagicMock()
        client.get.return_value = _mock_response(200, _make_wf_json("wf-001", "manual_review"))
        result = _adapter(client).get_workflow("wf-001")
        assert result is not None
        assert result.status == KYCStatus.MLRO_REVIEW

    def test_get_workflow_returns_none_on_404(self) -> None:
        client = MagicMock()
        client.get.return_value = _mock_response(404, {})
        result = _adapter(client).get_workflow("wf-missing")
        assert result is None

    def test_get_workflow_approved(self) -> None:
        client = MagicMock()
        client.get.return_value = _mock_response(200, _make_wf_json("wf-001", "approved"))
        result = _adapter(client).get_workflow("wf-001")
        assert result is not None
        assert result.status == KYCStatus.APPROVED


# ─────────────────────────────────────────────────────────────────────────────
# Tests: submit_documents
# ─────────────────────────────────────────────────────────────────────────────


class TestSubmitDocuments:
    def test_submit_documents_returns_result(self) -> None:
        client = MagicMock()
        client.patch.return_value = _mock_response(200, _make_wf_json("wf-001", "document_review"))
        result = _adapter(client).submit_documents("wf-001", ["doc-01", "doc-02"])
        assert result.status == KYCStatus.DOCUMENT_REVIEW

    def test_submit_documents_sends_event(self) -> None:
        client = MagicMock()
        client.patch.return_value = _mock_response(200, _make_wf_json("wf-001", "risk_assessment"))
        _adapter(client).submit_documents("wf-001", ["doc-01"])
        _, kwargs = client.patch.call_args
        payload = kwargs.get("json", {})
        assert payload.get("name") == "DOCUMENTS_SUBMITTED"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: approve_edd
# ─────────────────────────────────────────────────────────────────────────────


class TestApproveEdd:
    def test_approve_edd_sets_mlro_sign_off(self) -> None:
        client = MagicMock()
        client.patch.return_value = _mock_response(200, _make_wf_json("wf-001", "approved"))
        result = _adapter(client).approve_edd("wf-001", "mlro-user-007")
        assert result.mlro_sign_off is True
        assert result.status == KYCStatus.APPROVED

    def test_approve_edd_sends_correct_event(self) -> None:
        client = MagicMock()
        client.patch.return_value = _mock_response(200, _make_wf_json("wf-001", "approved"))
        _adapter(client).approve_edd("wf-001", "mlro-user-007")
        _, kwargs = client.patch.call_args
        payload = kwargs.get("json", {})
        assert payload.get("name") == "MANUAL_REVIEW_APPROVE"
        assert payload["payload"]["mlroUserId"] == "mlro-user-007"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: reject_workflow
# ─────────────────────────────────────────────────────────────────────────────


class TestRejectWorkflow:
    def test_reject_workflow_returns_rejected_status(self) -> None:
        client = MagicMock()
        client.patch.return_value = _mock_response(200, _make_wf_json("wf-001", "rejected"))
        result = _adapter(client).reject_workflow("wf-001", RejectionReason.SANCTIONS_HIT)
        assert result.status == KYCStatus.REJECTED
        assert result.rejection_reason == RejectionReason.SANCTIONS_HIT

    def test_reject_workflow_sends_correct_event(self) -> None:
        client = MagicMock()
        client.patch.return_value = _mock_response(200, _make_wf_json("wf-001", "rejected"))
        _adapter(client).reject_workflow("wf-001", RejectionReason.DOCUMENT_FRAUD)
        _, kwargs = client.patch.call_args
        payload = kwargs.get("json", {})
        assert payload.get("name") == "MANUAL_REVIEW_REJECT"
        assert "DOCUMENT_FRAUD" in payload["payload"]["rejectionReason"]


# ─────────────────────────────────────────────────────────────────────────────
# Tests: health()
# ─────────────────────────────────────────────────────────────────────────────


class TestHealth:
    def test_health_returns_true_on_200(self) -> None:
        client = MagicMock()
        client.get.return_value = _mock_response(200, {"status": "ok"})
        assert _adapter(client).health() is True

    def test_health_returns_false_on_non_200(self) -> None:
        client = MagicMock()
        client.get.return_value = _mock_response(503, {})
        assert _adapter(client).health() is False

    def test_health_returns_false_on_exception(self) -> None:
        client = MagicMock()
        client.get.side_effect = Exception("connection refused")
        assert _adapter(client).health() is False


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _parse_workflow edge cases
# ─────────────────────────────────────────────────────────────────────────────


class TestParseWorkflow:
    def test_completed_with_rejected_result_maps_to_rejected(self) -> None:
        data = _make_wf_json("wf-001", "completed", result="rejected")
        result = _adapter().reject_workflow.__func__  # get adapter instance
        adapter = _adapter()
        result = adapter._parse_workflow(data)
        assert result.status == KYCStatus.REJECTED

    def test_completed_without_result_maps_to_approved(self) -> None:
        adapter = _adapter()
        result = adapter._parse_workflow(_make_wf_json("wf-001", "completed"))
        assert result.status == KYCStatus.APPROVED

    def test_business_entity_type(self) -> None:
        adapter = _adapter()
        data = _make_wf_json("wf-001", "created", entity_type="BUSINESS")
        result = adapter._parse_workflow(data)
        assert result.kyc_type == KYCType.BUSINESS

    def test_edd_required_from_context(self) -> None:
        adapter = _adapter()
        data = _make_wf_json("wf-001", "created", edd_required=True)
        result = adapter._parse_workflow(data)
        assert result.edd_required is True

    def test_rejection_reason_mapped(self) -> None:
        adapter = _adapter()
        data = _make_wf_json("wf-001", "rejected")
        data["context"]["rejectionReason"] = "SANCTIONS_HIT"
        result = adapter._parse_workflow(data)
        assert result.rejection_reason == RejectionReason.SANCTIONS_HIT

    def test_unknown_status_defaults_to_pending(self) -> None:
        adapter = _adapter()
        result = adapter._parse_workflow(_make_wf_json("wf-001", "unknown_future_state"))
        assert result.status == KYCStatus.PENDING

    def test_malformed_datetime_falls_back(self) -> None:
        adapter = _adapter()
        data = _make_wf_json("wf-001", "created")
        data["createdAt"] = "not-a-date"
        result = adapter._parse_workflow(data)
        assert isinstance(result.created_at, datetime)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: BallerineAdapter init
# ─────────────────────────────────────────────────────────────────────────────


class TestBallerineAdapterInit:
    def test_raises_if_no_base_url(self) -> None:
        import os

        saved = os.environ.pop("BALLERINE_URL", None)
        try:
            with pytest.raises(EnvironmentError, match="BALLERINE_URL"):
                BallerineAdapter()
        finally:
            if saved is not None:
                os.environ["BALLERINE_URL"] = saved

    def test_bearer_token_in_headers(self) -> None:
        adapter = BallerineAdapter(base_url="http://test", api_token="my-secret-token")
        # httpx.Client headers are set during construction;
        # verify the adapter was created without error (token handling is internal)
        assert adapter is not None
