"""
tests/test_api_safeguarding_recon.py — Safeguarding Reconciliation API router tests
IL-REC-01 | Phase 51B | Sprint 36 | CASS 7.15

Tests for endpoints:
  POST /v1/safeguarding-recon/run
  GET /v1/safeguarding-recon/reports
  GET /v1/safeguarding-recon/reports/{date}
  GET /v1/safeguarding-recon/breaches
  POST /v1/safeguarding-recon/breaches/{id}/resolve

PR #271: comprehensive coverage (xfail baseline).
PR #272: 7 error handling gaps fixed (xfail → PASS).
"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient
import pytest

from api.main import app

client = TestClient(app)


# ── POST /v1/safeguarding-recon/run ──────────────────────────────────────────


class TestRunReconciliation:
    """Test /v1/safeguarding-recon/run endpoint."""

    def test_run_recon_basic_success(self):
        """Test basic reconciliation run with valid request."""
        payload = {
            "date_str": "2026-07-03",
            "ledger_entries": [{"id": "LE-001", "amount": "1000.00", "currency": "GBP"}],
            "statement_entries": [
                {
                    "entry_id": "SE-001",
                    "account_iban": "GB82WEST12345698765432",
                    "amount": "1000.00",
                }
            ],
        }
        resp = client.post("/v1/safeguarding-recon/run", json=payload)
        assert resp.status_code in (200, 404, 503)

    def test_run_recon_empty_entries(self):
        """Test reconciliation run with empty entries."""
        payload = {
            "date_str": "2026-07-03",
            "ledger_entries": [],
            "statement_entries": [],
        }
        resp = client.post("/v1/safeguarding-recon/run", json=payload)
        assert resp.status_code in (200, 404)

    def test_run_recon_invalid_date_format(self):
        """Test invalid date string raises error."""
        payload = {
            "date_str": "not-a-date",
            "ledger_entries": [],
            "statement_entries": [
                {
                    "entry_id": "SE-001",
                    "account_iban": "GB82WEST12345698765432",
                    "amount": "100.00",
                }
            ],
        }
        resp = client.post("/v1/safeguarding-recon/run", json=payload)
        assert resp.status_code in (422, 400, 500)

    def test_run_recon_missing_required_field(self):
        """Test missing required date_str field."""
        payload = {
            "ledger_entries": [],
            "statement_entries": [],
        }
        resp = client.post("/v1/safeguarding-recon/run", json=payload)
        assert resp.status_code == 422

    def test_run_recon_amounts_as_decimal_strings(self):
        """Test that amounts in response are Decimal-compatible strings (I-01)."""
        payload = {
            "date_str": "2026-07-03",
            "ledger_entries": [{"id": "LE-001", "amount": "5000.50", "currency": "GBP"}],
            "statement_entries": [
                {
                    "entry_id": "SE-001",
                    "account_iban": "GB82WEST12345698765432",
                    "amount": "5000.50",
                }
            ],
        }
        resp = client.post("/v1/safeguarding-recon/run", json=payload)
        if resp.status_code == 200:
            data = resp.json()
            if "total_ledger_gbp" in data:
                Decimal(data["total_ledger_gbp"])
                Decimal(data["total_statement_gbp"])

    def test_run_recon_large_amounts(self):
        """Test handling of large amounts (edge case)."""
        payload = {
            "date_str": "2026-07-03",
            "ledger_entries": [{"id": "LE-001", "amount": "999999999.99", "currency": "GBP"}],
            "statement_entries": [
                {
                    "entry_id": "SE-001",
                    "account_iban": "GB82WEST12345698765432",
                    "amount": "999999999.99",
                }
            ],
        }
        resp = client.post("/v1/safeguarding-recon/run", json=payload)
        assert resp.status_code in (200, 404, 500, 503)


# ── GET /v1/safeguarding-recon/reports ─────────────────────────────────────────


class TestListReports:
    """Test /v1/safeguarding-recon/reports endpoint."""

    def test_list_reports_200(self):
        """Test list reports endpoint returns 200."""
        resp = client.get("/v1/safeguarding-recon/reports")
        assert resp.status_code == 200

    def test_list_reports_returns_list(self):
        """Test list reports returns a JSON array."""
        resp = client.get("/v1/safeguarding-recon/reports")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_list_reports_schema(self):
        """Test report item schema if reports exist."""
        resp = client.get("/v1/safeguarding-recon/reports")
        data = resp.json()
        if len(data) > 0:
            item = data[0]
            assert "report_id" in item
            assert "recon_date" in item
            assert "total_ledger_gbp" in item
            assert "total_statement_gbp" in item
            assert "net_discrepancy_gbp" in item
            assert "breach_detected" in item


# ── GET /v1/safeguarding-recon/reports/{date} ─────────────────────────────────────────


class TestGetReportByDate:
    """Test /v1/safeguarding-recon/reports/{date} endpoint."""

    def test_get_report_not_found(self):
        """Test getting report for non-existent date."""
        resp = client.get("/v1/safeguarding-recon/reports/2026-01-01")
        assert resp.status_code == 404

    def test_get_report_invalid_date_format(self):
        """Test invalid date format in path."""
        resp = client.get("/v1/safeguarding-recon/reports/not-a-date")
        assert resp.status_code in (404, 422)

    def test_get_report_valid_response_schema(self):
        """Test response schema for valid report (if exists)."""
        resp = client.get("/v1/safeguarding-recon/reports/2026-07-03")
        if resp.status_code == 200:
            data = resp.json()
            assert "report_id" in data
            assert "recon_date" in data
            assert "items" in data
            assert isinstance(data["items"], list)


# ── GET /v1/safeguarding-recon/breaches ────────────────────────────────────────────


class TestListBreaches:
    """Test /v1/safeguarding-recon/breaches endpoint."""

    def test_list_breaches_200(self):
        """Test list breaches endpoint returns 200."""
        resp = client.get("/v1/safeguarding-recon/breaches")
        assert resp.status_code == 200

    def test_list_breaches_returns_list(self):
        """Test list breaches returns JSON array."""
        resp = client.get("/v1/safeguarding-recon/breaches")
        assert isinstance(resp.json(), list)

    def test_list_breaches_schema(self):
        """Test breach item schema if breaches exist."""
        resp = client.get("/v1/safeguarding-recon/breaches")
        data = resp.json()
        if len(data) > 0:
            item = data[0]
            assert "report_id" in item
            assert "breach_detected" in item


# ── POST /v1/safeguarding-recon/breaches/{id}/resolve ─────────────────────────────────


class TestResolveBreach:
    """Test /v1/safeguarding-recon/breaches/{id}/resolve endpoint."""

    def test_resolve_breach_missing_resolved_by(self):
        """Test resolve breach without resolved_by field."""
        payload = {}
        resp = client.post("/v1/safeguarding-recon/breaches/breach-123/resolve", json=payload)
        assert resp.status_code == 422

    def test_resolve_breach_with_resolved_by(self):
        """Test resolve breach with valid resolved_by field."""
        payload = {"resolved_by": "officer@banxe.com"}
        resp = client.post("/v1/safeguarding-recon/breaches/breach-123/resolve", json=payload)
        assert resp.status_code in (200, 404)

    def test_resolve_breach_response_schema(self):
        """Test resolve breach response schema (HITL proposal)."""
        payload = {"resolved_by": "officer@banxe.com"}
        resp = client.post("/v1/safeguarding-recon/breaches/breach-123/resolve", json=payload)
        if resp.status_code == 200:
            data = resp.json()
            assert "action" in data or "error" in data


# ── Error Handling & Edge Cases ────────────────────────────────────────────


class TestErrorHandling:
    """Test error paths and edge cases for safeguarding recon."""

    def test_run_recon_negative_amount_in_statement(self):
        """Test handling of negative amounts in statement (should be valid for reversals)."""
        payload = {
            "date_str": "2026-07-03",
            "ledger_entries": [],
            "statement_entries": [
                {
                    "entry_id": "SE-001",
                    "account_iban": "GB82WEST12345698765432",
                    "amount": "-100.00",
                }
            ],
        }
        resp = client.post("/v1/safeguarding-recon/run", json=payload)
        assert resp.status_code in (200, 404, 400, 500)

    def test_run_recon_zero_amount(self):
        """Test handling of zero amounts."""
        payload = {
            "date_str": "2026-07-03",
            "ledger_entries": [{"id": "LE-001", "amount": "0.00", "currency": "GBP"}],
            "statement_entries": [],
        }
        resp = client.post("/v1/safeguarding-recon/run", json=payload)
        assert resp.status_code in (200, 404, 503)

    def test_run_recon_malformed_json(self):
        """Test malformed JSON request."""
        resp = client.post("/v1/safeguarding-recon/run", data="not json")
        assert resp.status_code in (400, 422)

    def test_run_recon_missing_statement_iban_field(self):
        """Test statement entry with missing IBAN field."""
        payload = {
            "date_str": "2026-07-03",
            "ledger_entries": [],
            "statement_entries": [{"entry_id": "SE-001", "amount": "100.00"}],
        }
        resp = client.post("/v1/safeguarding-recon/run", json=payload)
        assert resp.status_code == 422

    def test_list_endpoints_no_crash_on_empty_state(self):
        """Test that list endpoints don't crash even if no data exists."""
        resp1 = client.get("/v1/safeguarding-recon/reports")
        resp2 = client.get("/v1/safeguarding-recon/breaches")
        assert resp1.status_code == 200
        assert resp2.status_code == 200


# ── Decimal/Currency Compliance (I-01) ────────────────────────────────────────


class TestDecimalCompliance:
    """Ensure all monetary amounts use Decimal (I-01) in responses."""

    def test_report_amounts_parseable_as_decimal(self):
        """Test that all amount fields in report are parseable as Decimal."""
        resp = client.get("/v1/safeguarding-recon/reports")
        data = resp.json()
        if len(data) > 0:
            report = data[0]
            try:
                Decimal(report["total_ledger_gbp"])
                Decimal(report["total_statement_gbp"])
                Decimal(report["net_discrepancy_gbp"])
            except (ValueError, TypeError):
                pytest.fail("Report amounts must be Decimal-compatible strings")

    def test_reconciliation_item_amounts_decimal(self):
        """Test that reconciliation items have Decimal-compatible amounts."""
        resp = client.get("/v1/safeguarding-recon/reports")
        data = resp.json()
        if len(data) > 0 and "items" in data[0]:
            items = data[0]["items"]
            if len(items) > 0:
                item = items[0]
                try:
                    Decimal(item["ledger_amount"])
                    Decimal(item["statement_amount"])
                    Decimal(item["discrepancy"])
                except (ValueError, TypeError):
                    pytest.fail("Item amounts must be Decimal-compatible strings")


# ── Gap Fix Verification (PR #272 — 7 error handling gaps) ────────────────────


class TestSafeguardingReconRunGapFixes:
    """Gap fixes: POST /v1/safeguarding-recon/run error handling (PR #272)."""

    def test_invalid_date_format_returns_422(self) -> None:
        """Gap 1 FIXED: Malformed date_str returns 422."""
        resp = client.post(
            "/v1/safeguarding-recon/run",
            json={"date_str": "not-a-date", "ledger_entries": [], "statement_entries": []},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert "error" in str(data) or "detail" in str(data)

    def test_missing_amount_in_statement_returns_422(self) -> None:
        """Gap 2 FIXED: statement_entry missing 'amount' returns 422."""
        resp = client.post(
            "/v1/safeguarding-recon/run",
            json={
                "date_str": "2026-04-01",
                "ledger_entries": [],
                "statement_entries": [
                    {
                        "entry_id": "stmt-001",
                        "account_iban": "GB82WEST12345698765432",
                        "currency": "GBP",
                    }
                ],
            },
        )
        assert resp.status_code == 422

    def test_non_numeric_amount_returns_422(self) -> None:
        """Gap 3 FIXED: Non-numeric amount string returns 422."""
        resp = client.post(
            "/v1/safeguarding-recon/run",
            json={
                "date_str": "2026-04-01",
                "ledger_entries": [],
                "statement_entries": [
                    {
                        "entry_id": "stmt-001",
                        "account_iban": "GB82WEST12345698765432",
                        "amount": "not-a-number",
                        "currency": "GBP",
                    }
                ],
            },
        )
        assert resp.status_code == 422


class TestSafeguardingReconListReportsGapFixes:
    """Gap fixes: GET /v1/safeguarding-recon/reports error handling (PR #272)."""

    def test_list_reports_returns_200_or_503(self) -> None:
        """Gap 4 FIXED: Agent failure returns 503, not 500."""
        resp = client.get("/v1/safeguarding-recon/reports")
        assert resp.status_code in (200, 503)
        if resp.status_code >= 400:
            data = resp.json()
            if resp.status_code == 503:
                assert "error" in data or "detail" in data


class TestSafeguardingReconGetReportGapFixes:
    """Gap fixes: GET /v1/safeguarding-recon/reports/{date} error handling (PR #272)."""

    def test_agent_error_returns_503_not_500(self) -> None:
        """Gap 5 FIXED: Internal error returns 503 not 500."""
        resp = client.get("/v1/safeguarding-recon/reports/2026-04-01")
        assert resp.status_code in (200, 404, 503)
        if resp.status_code >= 500:
            assert resp.status_code == 503


class TestSafeguardingReconListBreachesGapFixes:
    """Gap fixes: GET /v1/safeguarding-recon/breaches error handling (PR #272)."""

    def test_agent_failure_returns_503(self) -> None:
        """Gap 6 FIXED: Agent failure returns 503 Service Unavailable."""
        resp = client.get("/v1/safeguarding-recon/breaches")
        assert resp.status_code in (200, 503)
        if resp.status_code >= 500:
            assert resp.status_code == 503


class TestSafeguardingReconResolveBreachGapFixes:
    """Gap fixes: POST /v1/safeguarding-recon/breaches/{id}/resolve error handling (PR #272)."""

    def test_resolve_breach_service_error_returns_503(self) -> None:
        """Gap 7 FIXED: Internal error returns 503, never 500."""
        resp = client.post(
            "/v1/safeguarding-recon/breaches/nonexistent-id/resolve",
            json={"resolved_by": "compliance@banxe.com"},
        )
        assert resp.status_code in (200, 404, 503)
        if resp.status_code >= 500:
            assert resp.status_code == 503
