"""
tests/test_merchant_acquiring/test_api_merchant.py
IL-MAG-01 | Phase 20 — Merchant Acquiring REST API tests.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import merchant_acquiring as ma_router

# Minimal test app — router registered separately in api/main.py
_test_app = FastAPI()
_test_app.include_router(ma_router.router, prefix="/v1")

client = TestClient(_test_app)

BASE = "/v1/merchants"


def _mock_agent(overrides: dict | None = None):
    """Create a mock MerchantAgent with sensible defaults."""
    mock = AsyncMock()
    merchant_dict = {
        "id": "m-001",
        "name": "Test Shop",
        "legal_name": "Test Shop Ltd",
        "mcc": "5411",
        "country": "GB",
        "website": None,
        "status": "ACTIVE",
        "risk_tier": "LOW",
        "onboarded_at": "2026-01-01T00:00:00+00:00",
        "daily_limit": "10000",
        "monthly_limit": "200000",
    }
    payment_dict = {
        "id": "p-001",
        "merchant_id": "m-001",
        "amount": "20.00",
        "currency": "GBP",
        "result": "APPROVED",
        "card_last_four": "4242",
        "reference": "ref-001",
        "requires_3ds": False,
        "created_at": "2026-01-01T00:00:00+00:00",
        "completed_at": "2026-01-01T00:00:00+00:00",
        "acquirer_ref": "ACQ-ABCDEF",
    }
    settlement_dict = {
        "id": "s-001",
        "merchant_id": "m-001",
        "settlement_date": "2026-01-01T00:00:00+00:00",
        "gross_amount": "20.00",
        "fees": "0.30",
        "net_amount": "19.70",
        "payment_count": 1,
        "status": "PENDING",
        "bank_reference": None,
    }
    dispute_dict = {
        "id": "d-001",
        "merchant_id": "m-001",
        "payment_id": "p-001",
        "amount": "20.00",
        "currency": "GBP",
        "reason": "FRAUD",
        "status": "RECEIVED",
        "received_at": "2026-01-01T00:00:00+00:00",
        "resolved_at": None,
        "evidence_submitted": False,
    }
    score_dict = {
        "merchant_id": "m-001",
        "computed_at": "2026-01-01T00:00:00+00:00",
        "chargeback_ratio": 0.0,
        "volume_anomaly": 0.0,
        "mcc_risk": 10.0,
        "overall_score": 3.0,
        "risk_tier": "LOW",
    }
    mock.onboard_merchant = AsyncMock(return_value=merchant_dict)
    mock.approve_kyb = AsyncMock(return_value=merchant_dict)
    mock.get_merchant = AsyncMock(return_value=merchant_dict)
    mock.list_merchants = AsyncMock(return_value=[merchant_dict])
    mock.accept_payment = AsyncMock(return_value=payment_dict)
    mock.complete_3ds = AsyncMock(return_value={**payment_dict, "result": "APPROVED"})
    mock.create_settlement = AsyncMock(return_value=settlement_dict)
    mock.list_settlements = AsyncMock(return_value=[settlement_dict])
    mock.receive_chargeback = AsyncMock(return_value=dispute_dict)
    mock.resolve_dispute = AsyncMock(return_value={**dispute_dict, "status": "RESOLVED_WIN"})
    mock.score_merchant = AsyncMock(return_value=score_dict)
    mock.get_audit_log = AsyncMock(return_value=[])

    if overrides:
        for k, v in overrides.items():
            setattr(mock, k, v)
    return mock


def test_post_merchants_onboard_returns_200() -> None:
    with patch("api.routers.merchant_acquiring._get_agent", return_value=_mock_agent()):
        resp = client.post(
            f"{BASE}/onboard",
            json={
                "name": "Shop",
                "legal_name": "Shop Ltd",
                "mcc": "5411",
                "country": "GB",
                "daily_limit": "5000",
                "monthly_limit": "100000",
                "actor": "admin",
            },
        )
    assert resp.status_code == 200


def test_post_merchants_onboard_prohibited_mcc_returns_422() -> None:
    mock = _mock_agent()
    mock.onboard_merchant = AsyncMock(side_effect=ValueError("MCC prohibited"))
    with patch("api.routers.merchant_acquiring._get_agent", return_value=mock):
        resp = client.post(
            f"{BASE}/onboard",
            json={
                "name": "Casino",
                "legal_name": "Casino Ltd",
                "mcc": "7995",
                "country": "GB",
                "daily_limit": "5000",
                "monthly_limit": "100000",
                "actor": "admin",
            },
        )
    assert resp.status_code == 422


def test_post_merchants_approve_kyb_returns_200() -> None:
    with patch("api.routers.merchant_acquiring._get_agent", return_value=_mock_agent()):
        resp = client.post(f"{BASE}/m-001/approve-kyb")
    assert resp.status_code == 200


def test_get_merchant_by_id_returns_200() -> None:
    with patch("api.routers.merchant_acquiring._get_agent", return_value=_mock_agent()):
        resp = client.get(f"{BASE}/m-001")
    assert resp.status_code == 200


def test_get_merchants_list_returns_200() -> None:
    with patch("api.routers.merchant_acquiring._get_agent", return_value=_mock_agent()):
        resp = client.get(BASE)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_post_payments_returns_200() -> None:
    with patch("api.routers.merchant_acquiring._get_agent", return_value=_mock_agent()):
        resp = client.post(
            f"{BASE}/m-001/payments",
            json={
                "amount": "20.00",
                "currency": "GBP",
                "card_last_four": "4242",
                "reference": "ref-001",
                "actor": "admin",
            },
        )
    assert resp.status_code == 200


def test_post_3ds_returns_200() -> None:
    with patch("api.routers.merchant_acquiring._get_agent", return_value=_mock_agent()):
        resp = client.post(f"{BASE}/payments/p-001/3ds")
    assert resp.status_code == 200
    assert resp.json()["result"] == "APPROVED"


def test_get_settlements_returns_200_list() -> None:
    with patch("api.routers.merchant_acquiring._get_agent", return_value=_mock_agent()):
        resp = client.get(f"{BASE}/m-001/settlements")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_post_settlements_returns_200() -> None:
    with patch("api.routers.merchant_acquiring._get_agent", return_value=_mock_agent()):
        resp = client.post(f"{BASE}/m-001/settlements")
    assert resp.status_code == 200


def test_post_chargebacks_returns_200() -> None:
    with patch("api.routers.merchant_acquiring._get_agent", return_value=_mock_agent()):
        resp = client.post(
            f"{BASE}/m-001/chargebacks",
            json={
                "payment_id": "p-001",
                "amount": "20.00",
                "currency": "GBP",
                "reason": "FRAUD",
                "actor": "admin",
            },
        )
    assert resp.status_code == 200


def test_get_risk_score_returns_200() -> None:
    with patch("api.routers.merchant_acquiring._get_agent", return_value=_mock_agent()):
        resp = client.get(f"{BASE}/m-001/risk-score")
    assert resp.status_code == 200


def test_get_unknown_merchant_returns_404() -> None:
    mock = _mock_agent()
    mock.get_merchant = AsyncMock(return_value=None)
    with patch("api.routers.merchant_acquiring._get_agent", return_value=mock):
        resp = client.get(f"{BASE}/unknown-id")
    assert resp.status_code == 404


def test_payment_request_amount_is_string() -> None:
    with patch("api.routers.merchant_acquiring._get_agent", return_value=_mock_agent()):
        resp = client.post(
            f"{BASE}/m-001/payments",
            json={
                "amount": "99.99",
                "currency": "GBP",
                "card_last_four": "1234",
                "reference": "str-ref",
                "actor": "admin",
            },
        )
    assert resp.status_code == 200
    # amount in payload was a string; gateway should have received it as string


def test_full_onboard_and_payment_flow_via_api() -> None:
    mock = _mock_agent()
    with patch("api.routers.merchant_acquiring._get_agent", return_value=mock):
        onboard_resp = client.post(
            f"{BASE}/onboard",
            json={
                "name": "FullFlow",
                "legal_name": "FF Ltd",
                "mcc": "5411",
                "country": "GB",
                "daily_limit": "5000",
                "monthly_limit": "100000",
                "actor": "admin",
            },
        )
        assert onboard_resp.status_code == 200
        mid = onboard_resp.json()["id"]

        approve_resp = client.post(f"{BASE}/{mid}/approve-kyb")
        assert approve_resp.status_code == 200

        payment_resp = client.post(
            f"{BASE}/{mid}/payments",
            json={
                "amount": "20.00",
                "currency": "GBP",
                "card_last_four": "4242",
                "reference": "ref",
                "actor": "admin",
            },
        )
        assert payment_resp.status_code == 200
