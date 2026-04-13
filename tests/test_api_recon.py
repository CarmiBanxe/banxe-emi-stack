"""
tests/test_api_recon.py — Reconciliation API router tests
GAP-010 D-recon | CASS 7.15.17R | CASS 7.15.29R | banxe-emi-stack

Tests:
  GET /v1/recon/status   — latest reconciliation status
  GET /v1/recon/report   — full tri-party report
  GET /v1/recon/history  — reconciliation history
"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


# ── GET /v1/recon/status ──────────────────────────────────────────────────────


class TestReconStatus:
    def test_returns_200(self):
        resp = client.get("/v1/recon/status")
        assert resp.status_code == 200

    def test_response_schema(self):
        data = client.get("/v1/recon/status").json()
        assert "settlement_date" in data
        assert "overall_status" in data
        assert "is_compliant" in data
        assert "rails_net_gbp" in data
        assert "midaz_client_funds_gbp" in data
        assert "generated_at" in data

    def test_sandbox_matched(self):
        data = client.get("/v1/recon/status").json()
        assert data["overall_status"] == "MATCHED"
        assert data["is_compliant"] is True

    def test_amounts_decimal_strings(self):
        data = client.get("/v1/recon/status").json()
        Decimal(data["rails_net_gbp"])
        Decimal(data["midaz_client_funds_gbp"])

    def test_sandbox_bank_balance_present(self):
        data = client.get("/v1/recon/status").json()
        # Stub bank returns a balance
        assert data["safeguarding_bank_gbp"] is not None
        Decimal(data["safeguarding_bank_gbp"])

    def test_with_as_of_query(self):
        resp = client.get("/v1/recon/status?as_of=2026-04-01")
        assert resp.status_code == 200
        assert resp.json()["settlement_date"] == "2026-04-01"

    def test_invalid_date_raises(self):
        resp = client.get("/v1/recon/status?as_of=bad-date")
        assert resp.status_code in (422, 500)


# ── GET /v1/recon/report ──────────────────────────────────────────────────────


class TestReconReport:
    def test_returns_200(self):
        resp = client.get("/v1/recon/report")
        assert resp.status_code == 200

    def test_response_schema(self):
        data = client.get("/v1/recon/report").json()
        assert "settlement_date" in data
        assert "overall_status" in data
        assert "is_compliant" in data
        assert "rails_net_gbp" in data
        assert "rails_transaction_count" in data
        assert "midaz_client_funds_gbp" in data
        assert "midaz_operational_gbp" in data
        assert "legs" in data
        assert "run_at" in data
        assert "generated_at" in data

    def test_three_legs_present(self):
        data = client.get("/v1/recon/report").json()
        assert len(data["legs"]) == 3

    def test_leg_schema(self):
        data = client.get("/v1/recon/report").json()
        leg = data["legs"][0]
        assert "leg" in leg
        assert "left_gbp" in leg
        assert "right_gbp" in leg
        assert "difference_gbp" in leg
        assert "tolerance_gbp" in leg
        assert "status" in leg

    def test_sandbox_all_legs_matched(self):
        data = client.get("/v1/recon/report").json()
        for leg in data["legs"]:
            assert leg["status"] == "MATCHED"

    def test_leg_names(self):
        data = client.get("/v1/recon/report").json()
        leg_names = {leg["leg"] for leg in data["legs"]}
        assert "RAILS_VS_LEDGER" in leg_names
        assert "LEDGER_VS_BANK" in leg_names
        assert "RAILS_VS_BANK" in leg_names

    def test_transaction_count_positive(self):
        data = client.get("/v1/recon/report").json()
        assert data["rails_transaction_count"] > 0

    def test_amounts_decimal_strings(self):
        data = client.get("/v1/recon/report").json()
        Decimal(data["rails_net_gbp"])
        Decimal(data["midaz_client_funds_gbp"])
        Decimal(data["midaz_operational_gbp"])

    def test_with_as_of_query(self):
        resp = client.get("/v1/recon/report?as_of=2026-04-01")
        assert resp.status_code == 200
        assert resp.json()["settlement_date"] == "2026-04-01"

    def test_bank_source_file_present(self):
        data = client.get("/v1/recon/report").json()
        assert data["safeguarding_source_file"] is not None


# ── GET /v1/recon/history ─────────────────────────────────────────────────────


class TestReconHistory:
    def test_returns_200(self):
        resp = client.get("/v1/recon/history")
        assert resp.status_code == 200

    def test_response_schema(self):
        data = client.get("/v1/recon/history").json()
        assert "days_requested" in data
        assert "entries" in data
        assert "generated_at" in data

    def test_default_7_days(self):
        data = client.get("/v1/recon/history").json()
        assert data["days_requested"] == 7
        assert len(data["entries"]) == 7

    def test_custom_days(self):
        data = client.get("/v1/recon/history?days=3").json()
        assert data["days_requested"] == 3
        assert len(data["entries"]) == 3

    def test_entry_schema(self):
        data = client.get("/v1/recon/history?days=1").json()
        entry = data["entries"][0]
        assert "settlement_date" in entry
        assert "overall_status" in entry
        assert "is_compliant" in entry
        assert "midaz_client_funds_gbp" in entry

    def test_sandbox_all_matched(self):
        data = client.get("/v1/recon/history?days=5").json()
        for entry in data["entries"]:
            assert entry["overall_status"] == "MATCHED"
            assert entry["is_compliant"] is True

    def test_days_above_max_422(self):
        resp = client.get("/v1/recon/history?days=91")
        assert resp.status_code == 422

    def test_days_below_min_422(self):
        resp = client.get("/v1/recon/history?days=0")
        assert resp.status_code == 422

    def test_amounts_decimal_strings(self):
        data = client.get("/v1/recon/history?days=1").json()
        for entry in data["entries"]:
            Decimal(entry["midaz_client_funds_gbp"])
