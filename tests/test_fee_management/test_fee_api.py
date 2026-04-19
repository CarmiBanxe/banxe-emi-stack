"""
tests/test_fee_management/test_fee_api.py
IL-FME-01 | Phase 41 | 16 tests
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


class TestGetFeeSchedule:
    def test_get_schedule_200(self) -> None:
        resp = client.get("/v1/fees/schedule")
        assert resp.status_code == 200

    def test_schedule_has_rules(self) -> None:
        resp = client.get("/v1/fees/schedule")
        data = resp.json()
        assert "rules" in data
        assert len(data["rules"]) > 0

    def test_schedule_amounts_are_strings(self) -> None:
        resp = client.get("/v1/fees/schedule")
        data = resp.json()
        for rule in data["rules"]:
            assert isinstance(rule["amount"], str)


class TestComparePlans:
    def test_compare_returns_200(self) -> None:
        resp = client.get("/v1/fees/schedule/compare?plan_a=plan-a&plan_b=plan-b")
        assert resp.status_code == 200

    def test_compare_response_structure(self) -> None:
        resp = client.get("/v1/fees/schedule/compare?plan_a=x&plan_b=y")
        data = resp.json()
        assert "plan_a" in data
        assert "plan_b" in data
        assert "difference" in data


class TestEstimateFees:
    def test_estimate_200(self) -> None:
        resp = client.post(
            "/v1/fees/estimate",
            json={
                "transactions": 10,
                "avg_amount": "100.00",
                "fx_volume": "0.00",
                "tier": "STANDARD",
            },
        )
        assert resp.status_code == 200

    def test_estimate_amount_string(self) -> None:
        resp = client.post(
            "/v1/fees/estimate",
            json={
                "transactions": 5,
                "avg_amount": "250.00",
                "fx_volume": "1000.00",
                "tier": "GOLD",
            },
        )
        data = resp.json()
        assert isinstance(data["estimated_annual_cost"], str)

    def test_estimate_invalid_amount_422(self) -> None:
        resp = client.post(
            "/v1/fees/estimate",
            json={
                "transactions": 5,
                "avg_amount": "not-a-number",
                "fx_volume": "0.00",
                "tier": "STANDARD",
            },
        )
        assert resp.status_code == 422


class TestListCharges:
    def test_list_charges_200(self) -> None:
        resp = client.get("/v1/fees/accounts/acc-api-test/charges")
        assert resp.status_code == 200

    def test_list_charges_structure(self) -> None:
        resp = client.get("/v1/fees/accounts/acc-api-test/charges")
        data = resp.json()
        assert "charges" in data


class TestApplyCharge:
    def test_apply_charge_200(self) -> None:
        resp = client.post(
            "/v1/fees/accounts/acc-api-test/charges",
            json={"rule_id": "rule-maintenance-001", "reference": "test-ref"},
        )
        assert resp.status_code == 200

    def test_apply_charge_unknown_rule_404(self) -> None:
        resp = client.post(
            "/v1/fees/accounts/acc-api-test/charges",
            json={"rule_id": "nonexistent", "reference": "test-ref"},
        )
        assert resp.status_code == 404


class TestGetOutstanding:
    def test_outstanding_200(self) -> None:
        resp = client.get("/v1/fees/accounts/acc-api-test/outstanding")
        assert resp.status_code == 200


class TestRequestWaiver:
    def test_waiver_returns_hitl(self) -> None:
        resp = client.post(
            "/v1/fees/accounts/acc-api-test/waivers",
            json={"charge_id": "charge-1", "reason": "GOODWILL", "requested_by": "user-1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "requires_approval_from" in data

    def test_invalid_reason_422(self) -> None:
        resp = client.post(
            "/v1/fees/accounts/acc-api-test/waivers",
            json={"charge_id": "charge-1", "reason": "INVALID_REASON", "requested_by": "user-1"},
        )
        assert resp.status_code == 422


class TestGetFeeSummary:
    def test_summary_200(self) -> None:
        resp = client.get("/v1/fees/accounts/acc-api-test/summary")
        assert resp.status_code == 200

    def test_summary_amounts_are_strings(self) -> None:
        resp = client.get("/v1/fees/accounts/acc-api-test/summary")
        data = resp.json()
        assert isinstance(data["total_charged"], str)
        assert isinstance(data["outstanding"], str)


class TestReconcileAccount:
    def test_reconcile_200(self) -> None:
        resp = client.post("/v1/fees/accounts/acc-api-test/reconcile")
        assert resp.status_code == 200

    def test_reconcile_status_field(self) -> None:
        resp = client.post("/v1/fees/accounts/acc-api-test/reconcile")
        data = resp.json()
        assert data["status"] in ("CLEAN", "DISCREPANCY")
