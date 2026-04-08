"""
tests/test_case_management.py — Case Management tests (IL-059)
EU AI Act Art.14 | FCA MLR 2017 §26 | banxe-emi-stack

Coverage:
  - CasePort dataclasses and enums
  - MockCaseAdapter: create, get, resolve, idempotency, helpers
  - MarbleAdapter: init validation, create/get/resolve, timeout/error fallbacks,
    payload builder, response parser, health
  - Factory: get_case_adapter()
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from services.case_management.case_port import (
    CaseOutcome,
    CasePriority,
    CaseRequest,
    CaseStatus,
    CaseType,
)
from services.case_management.mock_case_adapter import MockCaseAdapter


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _req(**kwargs) -> CaseRequest:
    defaults = dict(
        case_reference="tx-001",
        case_type=CaseType.FRAUD_REVIEW,
        entity_id="cust-001",
        entity_type="individual",
        priority=CasePriority.HIGH,
        description="High fraud score detected",
        amount=Decimal("500.00"),
        currency="GBP",
        risk_score=75,
        metadata={"factors": ["NewDevice", "HighRiskCountry"]},
    )
    defaults.update(kwargs)
    return CaseRequest(**defaults)


def _mock_http_response(status_code: int, json_data: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.is_error = status_code >= 400
    resp.json.return_value = json_data
    resp.text = str(json_data)[:200]
    return resp


def _marble(client: MagicMock | None = None):
    """Create MarbleAdapter with direct params, swap _client."""
    from services.case_management.marble_adapter import MarbleAdapter
    adapter = MarbleAdapter(
        base_url="http://marble-test:5002",
        api_key="test-api-key",
        inbox_id="inbox-guid-001",
        timeout_ms=5000,
    )
    adapter._client = client or MagicMock()
    return adapter


def _marble_case_json(
    case_id: str = "marble-case-001",
    status: str = "open",
    outcome: str = "",
    reference: str = "tx-001",
) -> dict:
    return {
        "id": case_id,
        "status": status,
        "outcome": outcome,
        "createdAt": "2026-04-09T10:00:00Z",
        "assignedTo": None,
        "metadata": {"banxe_reference": reference},
        "url": f"http://marble-test:5002/cases/{case_id}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# TestCasePortEnums
# ─────────────────────────────────────────────────────────────────────────────

class TestCasePortEnums:
    def test_case_type_values(self):
        assert CaseType.SAR.value == "SAR"
        assert CaseType.EDD.value == "EDD"
        assert CaseType.FRAUD_REVIEW.value == "FRAUD_REVIEW"
        assert CaseType.APP_SCAM.value == "APP_SCAM"
        assert CaseType.MLRO_REVIEW.value == "MLRO_REVIEW"

    def test_case_status_values(self):
        assert CaseStatus.OPEN.value == "OPEN"
        assert CaseStatus.INVESTIGATING.value == "INVESTIGATING"
        assert CaseStatus.RESOLVED.value == "RESOLVED"
        assert CaseStatus.CLOSED.value == "CLOSED"

    def test_case_outcome_values(self):
        assert CaseOutcome.APPROVED.value == "APPROVED"
        assert CaseOutcome.REJECTED.value == "REJECTED"
        assert CaseOutcome.ESCALATED.value == "ESCALATED"
        assert CaseOutcome.INCONCLUSIVE.value == "INCONCLUSIVE"

    def test_case_priority_values(self):
        assert CasePriority.LOW.value == "LOW"
        assert CasePriority.MEDIUM.value == "MEDIUM"
        assert CasePriority.HIGH.value == "HIGH"
        assert CasePriority.CRITICAL.value == "CRITICAL"


# ─────────────────────────────────────────────────────────────────────────────
# TestMockCaseAdapter
# ─────────────────────────────────────────────────────────────────────────────

class TestMockCaseAdapter:
    def test_create_case_returns_open(self):
        adapter = MockCaseAdapter()
        result = adapter.create_case(_req())

        assert result.status == CaseStatus.OPEN
        assert result.case_reference == "tx-001"
        assert result.provider == "mock"
        assert result.case_id.startswith("MOCK-CASE-")

    def test_create_case_idempotent(self):
        adapter = MockCaseAdapter()
        r1 = adapter.create_case(_req())
        r2 = adapter.create_case(_req())

        assert r1.case_id == r2.case_id
        assert adapter.case_count == 1

    def test_create_case_different_references(self):
        adapter = MockCaseAdapter()
        r1 = adapter.create_case(_req(case_reference="tx-001"))
        r2 = adapter.create_case(_req(case_reference="tx-002"))

        assert r1.case_id != r2.case_id
        assert adapter.case_count == 2

    def test_get_case_returns_current_state(self):
        adapter = MockCaseAdapter()
        created = adapter.create_case(_req())

        fetched = adapter.get_case(created.case_id)
        assert fetched.case_id == created.case_id
        assert fetched.status == CaseStatus.OPEN

    def test_get_case_not_found_returns_closed(self):
        adapter = MockCaseAdapter()
        result = adapter.get_case("nonexistent-id")
        assert result.status == CaseStatus.CLOSED

    def test_resolve_case_sets_resolved_status(self):
        adapter = MockCaseAdapter()
        created = adapter.create_case(_req())

        resolved = adapter.resolve_case(
            created.case_id,
            CaseOutcome.APPROVED,
            notes="MLRO approved after review",
        )
        assert resolved.status == CaseStatus.RESOLVED
        assert resolved.outcome == CaseOutcome.APPROVED

    def test_resolve_case_persisted(self):
        adapter = MockCaseAdapter()
        created = adapter.create_case(_req())
        adapter.resolve_case(created.case_id, CaseOutcome.REJECTED)

        fetched = adapter.get_case(created.case_id)
        assert fetched.status == CaseStatus.RESOLVED
        assert fetched.outcome == CaseOutcome.REJECTED

    def test_resolve_case_not_found_raises(self):
        adapter = MockCaseAdapter()
        with pytest.raises(KeyError):
            adapter.resolve_case("bad-id", CaseOutcome.APPROVED)

    def test_health_always_true(self):
        assert MockCaseAdapter().health() is True

    def test_get_all_cases(self):
        adapter = MockCaseAdapter()
        adapter.create_case(_req(case_reference="tx-001"))
        adapter.create_case(_req(case_reference="tx-002"))
        assert len(adapter.get_all_cases()) == 2

    def test_reset_clears_state(self):
        adapter = MockCaseAdapter()
        adapter.create_case(_req())
        adapter.reset()
        assert adapter.case_count == 0

    def test_all_case_types_accepted(self):
        adapter = MockCaseAdapter()
        for case_type in CaseType:
            result = adapter.create_case(_req(
                case_reference=f"ref-{case_type.value}",
                case_type=case_type,
            ))
            assert result.status == CaseStatus.OPEN

    def test_case_with_no_amount(self):
        adapter = MockCaseAdapter()
        result = adapter.create_case(_req(amount=None, currency=None))
        assert result.status == CaseStatus.OPEN

    def test_url_contains_case_id(self):
        adapter = MockCaseAdapter()
        result = adapter.create_case(_req())
        assert result.case_id in (result.url or "")


# ─────────────────────────────────────────────────────────────────────────────
# TestMarbleAdapterInit
# ─────────────────────────────────────────────────────────────────────────────

class TestMarbleAdapterInit:
    def test_direct_params_ok(self):
        adapter = _marble()
        assert adapter._base_url == "http://marble-test:5002"
        assert adapter._api_key == "test-api-key"
        assert adapter._inbox_id == "inbox-guid-001"

    def test_missing_url_raises(self):
        from services.case_management.marble_adapter import MarbleAdapter
        with pytest.raises(EnvironmentError, match="MARBLE_URL"):
            MarbleAdapter(base_url="", api_key="key", inbox_id="inbox")

    def test_missing_api_key_raises(self):
        from services.case_management.marble_adapter import MarbleAdapter
        with pytest.raises(EnvironmentError, match="MARBLE_API_KEY"):
            MarbleAdapter(base_url="http://marble:5002", api_key="", inbox_id="inbox")

    def test_missing_inbox_id_raises(self):
        from services.case_management.marble_adapter import MarbleAdapter
        with pytest.raises(EnvironmentError, match="MARBLE_INBOX_ID"):
            MarbleAdapter(base_url="http://marble:5002", api_key="key", inbox_id="")

    def test_trailing_slash_stripped(self):
        from services.case_management.marble_adapter import MarbleAdapter
        adapter = MarbleAdapter(
            base_url="http://marble:5002/",
            api_key="key",
            inbox_id="inbox",
        )
        assert adapter._base_url == "http://marble:5002"

    def test_httpx_not_installed_raises(self):
        import sys
        from services.case_management.marble_adapter import MarbleAdapter
        with patch.dict(sys.modules, {"httpx": None}):
            with pytest.raises(RuntimeError, match="httpx not installed"):
                MarbleAdapter(
                    base_url="http://marble:5002",
                    api_key="key",
                    inbox_id="inbox",
                )


# ─────────────────────────────────────────────────────────────────────────────
# TestMarbleCreateCase
# ─────────────────────────────────────────────────────────────────────────────

class TestMarbleCreateCase:
    def test_success_returns_open_case(self):
        client = MagicMock()
        client.post.return_value = _mock_http_response(201, _marble_case_json())
        adapter = _marble(client)

        result = adapter.create_case(_req())

        assert result.case_id == "marble-case-001"
        assert result.status == CaseStatus.OPEN
        assert result.provider == "marble"
        assert result.case_reference == "tx-001"

    def test_payload_includes_inbox_id(self):
        client = MagicMock()
        client.post.return_value = _mock_http_response(201, _marble_case_json())
        adapter = _marble(client)

        adapter.create_case(_req())

        payload = client.post.call_args[1]["json"]
        assert payload["inboxId"] == "inbox-guid-001"

    def test_payload_name_contains_case_type(self):
        client = MagicMock()
        client.post.return_value = _mock_http_response(201, _marble_case_json())
        adapter = _marble(client)

        adapter.create_case(_req(case_type=CaseType.SAR, case_reference="tx-sar-1"))

        payload = client.post.call_args[1]["json"]
        assert "SAR" in payload["name"]
        assert "tx-sar-1" in payload["name"]

    def test_payload_metadata_has_banxe_reference(self):
        client = MagicMock()
        client.post.return_value = _mock_http_response(201, _marble_case_json())
        adapter = _marble(client)

        adapter.create_case(_req(case_reference="tx-meta-1"))

        payload = client.post.call_args[1]["json"]
        assert payload["metadata"]["banxe_reference"] == "tx-meta-1"

    def test_payload_description_includes_risk_score(self):
        client = MagicMock()
        client.post.return_value = _mock_http_response(201, _marble_case_json())
        adapter = _marble(client)

        adapter.create_case(_req(risk_score=80))

        payload = client.post.call_args[1]["json"]
        assert "80" in payload["description"]

    def test_payload_description_includes_amount(self):
        client = MagicMock()
        client.post.return_value = _mock_http_response(201, _marble_case_json())
        adapter = _marble(client)

        adapter.create_case(_req(amount=Decimal("1500.00"), currency="GBP"))

        payload = client.post.call_args[1]["json"]
        assert "1500" in payload["description"]
        assert "GBP" in payload["description"]

    def test_http_error_returns_stub(self):
        client = MagicMock()
        client.post.return_value = _mock_http_response(503, {})
        adapter = _marble(client)

        result = adapter.create_case(_req())

        assert "marble_error" in result.provider
        assert result.status == CaseStatus.OPEN  # conservative: stay open

    def test_timeout_returns_stub(self):
        import httpx
        client = MagicMock()
        client.post.side_effect = httpx.TimeoutException("timeout")
        adapter = _marble(client)

        result = adapter.create_case(_req())

        assert "marble_timeout" in result.provider
        assert result.status == CaseStatus.OPEN


# ─────────────────────────────────────────────────────────────────────────────
# TestMarbleGetCase
# ─────────────────────────────────────────────────────────────────────────────

class TestMarbleGetCase:
    def test_success_returns_case(self):
        client = MagicMock()
        client.get.return_value = _mock_http_response(
            200, _marble_case_json(case_id="case-abc", status="investigating")
        )
        adapter = _marble(client)

        result = adapter.get_case("case-abc")

        assert result.case_id == "case-abc"
        assert result.status == CaseStatus.INVESTIGATING

    def test_get_url_contains_case_id(self):
        client = MagicMock()
        client.get.return_value = _mock_http_response(200, _marble_case_json())
        adapter = _marble(client)

        adapter.get_case("marble-case-001")

        url_called = client.get.call_args[0][0]
        assert "marble-case-001" in url_called

    def test_error_returns_stub(self):
        client = MagicMock()
        client.get.return_value = _mock_http_response(404, {})
        adapter = _marble(client)

        result = adapter.get_case("unknown")
        assert "marble_error" in result.provider

    def test_timeout_returns_stub(self):
        import httpx
        client = MagicMock()
        client.get.side_effect = httpx.TimeoutException("timeout")
        adapter = _marble(client)

        result = adapter.get_case("case-x")
        assert "marble_timeout" in result.provider


# ─────────────────────────────────────────────────────────────────────────────
# TestMarbleResolveCase
# ─────────────────────────────────────────────────────────────────────────────

class TestMarbleResolveCase:
    def test_success_resolved_approved(self):
        client = MagicMock()
        client.patch.return_value = _mock_http_response(
            200, _marble_case_json(status="resolved", outcome="approved")
        )
        adapter = _marble(client)

        result = adapter.resolve_case("case-001", CaseOutcome.APPROVED, "MLRO approved")

        assert result.status == CaseStatus.RESOLVED
        assert result.outcome == CaseOutcome.APPROVED

    def test_payload_maps_outcome_to_marble_string(self):
        client = MagicMock()
        client.patch.return_value = _mock_http_response(
            200, _marble_case_json(status="resolved", outcome="rejected")
        )
        adapter = _marble(client)

        adapter.resolve_case("case-001", CaseOutcome.REJECTED)

        payload = client.patch.call_args[1]["json"]
        assert payload["outcome"] == "rejected"
        assert payload["status"] == "resolved"

    def test_notes_included_as_comment(self):
        client = MagicMock()
        client.patch.return_value = _mock_http_response(
            200, _marble_case_json(status="resolved", outcome="escalated")
        )
        adapter = _marble(client)

        adapter.resolve_case("case-001", CaseOutcome.ESCALATED, notes="Referred to NCA")

        payload = client.patch.call_args[1]["json"]
        assert payload["comment"] == "Referred to NCA"

    def test_empty_notes_not_included(self):
        client = MagicMock()
        client.patch.return_value = _mock_http_response(
            200, _marble_case_json(status="resolved", outcome="approved")
        )
        adapter = _marble(client)

        adapter.resolve_case("case-001", CaseOutcome.APPROVED, notes="")

        payload = client.patch.call_args[1]["json"]
        assert "comment" not in payload

    def test_error_returns_stub(self):
        client = MagicMock()
        client.patch.return_value = _mock_http_response(500, {})
        adapter = _marble(client)

        result = adapter.resolve_case("case-001", CaseOutcome.APPROVED)
        assert "marble_error" in result.provider

    def test_timeout_returns_stub(self):
        import httpx
        client = MagicMock()
        client.patch.side_effect = httpx.TimeoutException("timeout")
        adapter = _marble(client)

        result = adapter.resolve_case("case-001", CaseOutcome.APPROVED)
        assert "marble_timeout" in result.provider


# ─────────────────────────────────────────────────────────────────────────────
# TestMarbleParseResponse
# ─────────────────────────────────────────────────────────────────────────────

class TestMarbleParseResponse:
    def _parse(self, data: dict, ref: str = "tx-001"):
        return _marble()._parse_case(data, ref)

    def test_open_status_mapped(self):
        result = self._parse({"id": "c1", "status": "open", "createdAt": "2026-01-01T00:00:00Z"})
        assert result.status == CaseStatus.OPEN

    def test_investigating_status_mapped(self):
        result = self._parse({"id": "c1", "status": "investigating", "createdAt": "2026-01-01T00:00:00Z"})
        assert result.status == CaseStatus.INVESTIGATING

    def test_resolved_status_mapped(self):
        result = self._parse({"id": "c1", "status": "resolved", "createdAt": "2026-01-01T00:00:00Z"})
        assert result.status == CaseStatus.RESOLVED

    def test_unknown_status_defaults_to_open(self):
        result = self._parse({"id": "c1", "status": "unknown_state", "createdAt": "2026-01-01T00:00:00Z"})
        assert result.status == CaseStatus.OPEN

    def test_outcome_approved_mapped(self):
        result = self._parse({"id": "c1", "status": "resolved", "outcome": "approved", "createdAt": "2026-01-01T00:00:00Z"})
        assert result.outcome == CaseOutcome.APPROVED

    def test_no_outcome_maps_to_none(self):
        result = self._parse({"id": "c1", "status": "open", "createdAt": "2026-01-01T00:00:00Z"})
        assert result.outcome is None

    def test_banxe_reference_from_metadata(self):
        result = self._parse({
            "id": "c1",
            "status": "open",
            "createdAt": "2026-01-01T00:00:00Z",
            "metadata": {"banxe_reference": "tx-from-meta"},
        })
        assert result.case_reference == "tx-from-meta"

    def test_bad_created_at_defaults_to_now(self):
        result = self._parse({"id": "c1", "status": "open", "createdAt": "not-a-date"})
        # Should not raise; created_at is close to now
        diff = abs((result.created_at - datetime.now(timezone.utc)).total_seconds())
        assert diff < 5

    def test_assigned_to_extracted(self):
        result = self._parse({
            "id": "c1", "status": "open",
            "createdAt": "2026-01-01T00:00:00Z",
            "assignee": {"email": "mlro@banxe.com"},
        })
        assert result.assigned_to == "mlro@banxe.com"

    def test_provider_is_marble(self):
        result = self._parse({"id": "c1", "status": "open", "createdAt": "2026-01-01T00:00:00Z"})
        assert result.provider == "marble"


# ─────────────────────────────────────────────────────────────────────────────
# TestMarbleHealth
# ─────────────────────────────────────────────────────────────────────────────

class TestMarbleHealth:
    def test_health_true_on_200(self):
        client = MagicMock()
        client.get.return_value = _mock_http_response(200, {"status": "ok"})
        assert _marble(client).health() is True

    def test_health_true_on_204(self):
        client = MagicMock()
        client.get.return_value = _mock_http_response(204, {})
        assert _marble(client).health() is True

    def test_health_false_on_500(self):
        client = MagicMock()
        client.get.return_value = _mock_http_response(500, {})
        assert _marble(client).health() is False

    def test_health_false_on_network_error(self):
        import httpx
        client = MagicMock()
        client.get.side_effect = httpx.ConnectError("refused")
        assert _marble(client).health() is False


# ─────────────────────────────────────────────────────────────────────────────
# TestCaseFactory
# ─────────────────────────────────────────────────────────────────────────────

class TestCaseFactory:
    def test_default_returns_mock(self):
        from services.case_management.case_factory import get_case_adapter
        with patch.dict("os.environ", {"CASE_ADAPTER": "mock"}):
            adapter = get_case_adapter()
        assert isinstance(adapter, MockCaseAdapter)

    def test_no_env_returns_mock(self):
        from services.case_management.case_factory import get_case_adapter
        import os
        original = os.environ.pop("CASE_ADAPTER", None)
        try:
            adapter = get_case_adapter()
            assert isinstance(adapter, MockCaseAdapter)
        finally:
            if original is not None:
                os.environ["CASE_ADAPTER"] = original

    def test_marble_case_requires_env_vars(self):
        from services.case_management.case_factory import get_case_adapter
        with patch.dict("os.environ", {
            "CASE_ADAPTER": "marble",
            "MARBLE_URL": "",
            "MARBLE_API_KEY": "",
            "MARBLE_INBOX_ID": "",
        }):
            with pytest.raises(EnvironmentError):
                get_case_adapter()


# ─────────────────────────────────────────────────────────────────────────────
# TestI27HumanOversight
# ─────────────────────────────────────────────────────────────────────────────

class TestI27HumanOversight:
    """
    EU AI Act Art.14 + I-27: Case management enforces human oversight.
    The adapter creates cases for HITL review; it never auto-resolves cases.
    """

    def test_create_case_never_resolves_automatically(self):
        """create_case must return OPEN — never auto-resolved."""
        adapter = MockCaseAdapter()
        for case_type in CaseType:
            result = adapter.create_case(_req(
                case_reference=f"ref-{case_type.value}",
                case_type=case_type,
            ))
            assert result.status == CaseStatus.OPEN, (
                f"Case {case_type} was auto-resolved — violates EU AI Act Art.14"
            )

    def test_resolve_requires_explicit_outcome(self):
        """resolve_case requires explicit CaseOutcome — no default 'auto-approve'."""
        # Must provide explicit outcome
        for outcome in CaseOutcome:
            adapter2 = MockCaseAdapter()
            c = adapter2.create_case(_req(case_reference=f"ref-{outcome.value}"))
            resolved = adapter2.resolve_case(c.case_id, outcome)
            assert resolved.outcome == outcome
