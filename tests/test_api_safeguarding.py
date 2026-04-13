"""
tests/test_api_safeguarding.py — Safeguarding API router tests
CASS 7.15.17R | CASS 7.15.29R | CASS 15.12.4R | banxe-emi-stack

Tests:
  GET  /v1/safeguarding/position         — daily client funds position
  GET  /v1/safeguarding/accounts         — safeguarding account list
  GET  /v1/safeguarding/breaches         — breach history log
  POST /v1/safeguarding/reconcile        — trigger daily reconciliation
  GET  /v1/safeguarding/resolution-pack  — export resolution pack
  POST /v1/safeguarding/fca-return       — generate monthly FCA return
"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


# ── GET /v1/safeguarding/position ──────────────────────────────────────────────


class TestSafeguardingPosition:
    def test_returns_200(self):
        resp = client.get("/v1/safeguarding/position")
        assert resp.status_code == 200

    def test_response_schema(self):
        resp = client.get("/v1/safeguarding/position")
        data = resp.json()
        assert "as_of" in data
        assert "total_client_funds_gbp" in data
        assert "total_safeguarded_gbp" in data
        assert "difference_gbp" in data
        assert "status" in data
        assert "is_compliant" in data
        assert "generated_at" in data

    def test_amounts_are_decimal_strings(self):
        data = client.get("/v1/safeguarding/position").json()
        # Must not raise — confirms valid Decimal
        Decimal(data["total_client_funds_gbp"])
        Decimal(data["total_safeguarded_gbp"])
        Decimal(data["difference_gbp"])

    def test_sandbox_balances_matched(self):
        data = client.get("/v1/safeguarding/position").json()
        # Sandbox stubs both return 100000.00, so difference=0, status=MATCHED
        assert Decimal(data["difference_gbp"]) == Decimal("0")
        assert data["status"] == "MATCHED"
        assert data["is_compliant"] is True

    def test_with_as_of_query(self):
        resp = client.get("/v1/safeguarding/position?as_of=2026-04-01")
        assert resp.status_code == 200
        assert resp.json()["as_of"] == "2026-04-01"

    def test_invalid_date_raises_500_or_422(self):
        resp = client.get("/v1/safeguarding/position?as_of=not-a-date")
        assert resp.status_code in (422, 500)


# ── GET /v1/safeguarding/accounts ─────────────────────────────────────────────


class TestSafeguardingAccounts:
    def test_returns_200(self):
        resp = client.get("/v1/safeguarding/accounts")
        assert resp.status_code == 200

    def test_returns_list(self):
        data = client.get("/v1/safeguarding/accounts").json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_account_schema(self):
        accounts = client.get("/v1/safeguarding/accounts").json()
        acc = accounts[0]
        assert "account_id" in acc
        assert "bank_name" in acc
        assert "account_number" in acc
        assert "sort_code" in acc
        assert "account_type" in acc
        assert "balance_gbp" in acc
        assert "is_active" in acc

    def test_barclays_account_present(self):
        accounts = client.get("/v1/safeguarding/accounts").json()
        ids = [a["account_id"] for a in accounts]
        assert "safeguarding-barclays-001" in ids

    def test_active_account_has_positive_balance(self):
        accounts = client.get("/v1/safeguarding/accounts").json()
        active = [a for a in accounts if a["is_active"]]
        for acc in active:
            assert Decimal(acc["balance_gbp"]) >= Decimal("0")

    def test_all_designated_safeguarding_type(self):
        accounts = client.get("/v1/safeguarding/accounts").json()
        for acc in accounts:
            assert acc["account_type"] == "DESIGNATED_SAFEGUARDING"


# ── GET /v1/safeguarding/breaches ─────────────────────────────────────────────


class TestSafeguardingBreaches:
    def test_returns_200(self):
        resp = client.get("/v1/safeguarding/breaches")
        assert resp.status_code == 200

    def test_returns_list(self):
        data = client.get("/v1/safeguarding/breaches").json()
        assert isinstance(data, list)

    def test_sandbox_no_breaches(self):
        # Sandbox: no breach history
        data = client.get("/v1/safeguarding/breaches").json()
        assert data == []

    def test_days_param(self):
        resp = client.get("/v1/safeguarding/breaches?days=7")
        assert resp.status_code == 200

    def test_days_max_boundary(self):
        resp = client.get("/v1/safeguarding/breaches?days=365")
        assert resp.status_code == 200

    def test_days_above_max_422(self):
        resp = client.get("/v1/safeguarding/breaches?days=366")
        assert resp.status_code == 422

    def test_severity_filter_minor(self):
        resp = client.get("/v1/safeguarding/breaches?severity=MINOR")
        assert resp.status_code == 200

    def test_severity_filter_critical(self):
        resp = client.get("/v1/safeguarding/breaches?severity=CRITICAL")
        assert resp.status_code == 200


# ── POST /v1/safeguarding/reconcile ───────────────────────────────────────────


class TestSafeguardingReconcile:
    def test_returns_200(self):
        resp = client.post("/v1/safeguarding/reconcile", json={"dry_run": True})
        assert resp.status_code == 200

    def test_response_schema(self):
        resp = client.post("/v1/safeguarding/reconcile", json={"dry_run": True})
        data = resp.json()
        assert "run_date" in data
        assert "status" in data
        assert "internal_balance_gbp" in data
        assert "audit_event_id" in data
        assert "exit_code" in data

    def test_sandbox_exit_code_matched(self):
        resp = client.post("/v1/safeguarding/reconcile", json={"dry_run": True})
        data = resp.json()
        # Sandbox stubs match → exit_code 0 (MATCHED)
        assert data["exit_code"] == 0

    def test_with_explicit_run_date(self):
        resp = client.post(
            "/v1/safeguarding/reconcile",
            json={"run_date": "2026-04-01", "dry_run": True},
        )
        assert resp.status_code == 200
        assert resp.json()["run_date"] == "2026-04-01"

    def test_internal_balance_decimal_string(self):
        data = client.post("/v1/safeguarding/reconcile", json={"dry_run": True}).json()
        Decimal(data["internal_balance_gbp"])

    def test_no_breach_alert_in_sandbox(self):
        data = client.post("/v1/safeguarding/reconcile", json={"dry_run": True}).json()
        assert data["breach_alert"] is None

    def test_audit_event_id_non_empty(self):
        data = client.post("/v1/safeguarding/reconcile", json={"dry_run": True}).json()
        assert data["audit_event_id"]

    def test_invalid_date_format(self):
        resp = client.post(
            "/v1/safeguarding/reconcile",
            json={"run_date": "not-a-date", "dry_run": True},
        )
        assert resp.status_code in (422, 500)


# ── GET /v1/safeguarding/resolution-pack ──────────────────────────────────────


class TestSafeguardingResolutionPack:
    def test_returns_200(self):
        resp = client.get("/v1/safeguarding/resolution-pack")
        assert resp.status_code == 200

    def test_response_schema(self):
        data = client.get("/v1/safeguarding/resolution-pack").json()
        assert "generated_at" in data
        assert "as_of" in data
        assert "client_funds_gbp" in data
        assert "safeguarded_gbp" in data
        assert "difference_gbp" in data
        assert "recon_status" in data
        assert "accounts" in data
        assert "open_breaches" in data
        assert "resolution_deadline_hours" in data

    def test_resolution_deadline_48h(self):
        data = client.get("/v1/safeguarding/resolution-pack").json()
        assert data["resolution_deadline_hours"] == 48

    def test_accounts_list_non_empty(self):
        data = client.get("/v1/safeguarding/resolution-pack").json()
        assert len(data["accounts"]) >= 1

    def test_amounts_are_decimal_strings(self):
        data = client.get("/v1/safeguarding/resolution-pack").json()
        Decimal(data["client_funds_gbp"])
        Decimal(data["safeguarded_gbp"])
        Decimal(data["difference_gbp"])

    def test_sandbox_no_open_breaches(self):
        data = client.get("/v1/safeguarding/resolution-pack").json()
        assert data["open_breaches"] == []

    def test_with_as_of_query(self):
        resp = client.get("/v1/safeguarding/resolution-pack?as_of=2026-04-01")
        assert resp.status_code == 200
        assert resp.json()["as_of"] == "2026-04-01"


# ── POST /v1/safeguarding/fca-return ──────────────────────────────────────────


class TestSafeguardingFcaReturn:
    _PAYLOAD = {"year": 2026, "month": 4, "firm_name": "Banxe AI Bank Ltd", "frn": "000000"}

    def test_returns_200(self):
        resp = client.post("/v1/safeguarding/fca-return", json=self._PAYLOAD)
        assert resp.status_code == 200

    def test_response_schema(self):
        data = client.post("/v1/safeguarding/fca-return", json=self._PAYLOAD).json()
        assert "period" in data
        assert "firm_name" in data
        assert "frn" in data
        assert "total_client_money_gbp" in data
        assert "total_safeguarded_gbp" in data
        assert "is_compliant" in data
        assert "generated_at" in data
        assert "csv_row" in data

    def test_period_format(self):
        data = client.post("/v1/safeguarding/fca-return", json=self._PAYLOAD).json()
        # FIN060Generator returns something like "2026-04"
        assert "2026" in data["period"]

    def test_sandbox_compliant(self):
        data = client.post("/v1/safeguarding/fca-return", json=self._PAYLOAD).json()
        # Equal balances → no shortfall → compliant
        assert data["is_compliant"] is True

    def test_amounts_decimal_strings(self):
        data = client.post("/v1/safeguarding/fca-return", json=self._PAYLOAD).json()
        Decimal(data["total_client_money_gbp"])
        Decimal(data["total_safeguarded_gbp"])

    def test_csv_row_is_dict(self):
        data = client.post("/v1/safeguarding/fca-return", json=self._PAYLOAD).json()
        assert isinstance(data["csv_row"], dict)

    def test_firm_name_echoed(self):
        data = client.post("/v1/safeguarding/fca-return", json=self._PAYLOAD).json()
        assert data["firm_name"] == "Banxe AI Bank Ltd"

    def test_frn_echoed(self):
        data = client.post("/v1/safeguarding/fca-return", json=self._PAYLOAD).json()
        assert data["frn"] == "000000"

    def test_invalid_month_422(self):
        resp = client.post(
            "/v1/safeguarding/fca-return",
            json={"year": 2026, "month": 13, "firm_name": "Test", "frn": "000000"},
        )
        assert resp.status_code == 422

    def test_invalid_year_too_early_422(self):
        resp = client.post(
            "/v1/safeguarding/fca-return",
            json={"year": 2019, "month": 4, "firm_name": "Test", "frn": "000000"},
        )
        assert resp.status_code == 422
