"""
tests/test_api_payments.py — Payment API endpoint tests
IL-046 | banxe-emi-stack
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from api.deps import get_payment_service
from api.main import app
from services.payment.mock_payment_adapter import MockPaymentAdapter

client = TestClient(app)


def _fps_payload(idempotency_key: str | None = None) -> dict:
    return {
        "rail": "FPS",
        "amount": "100.00",
        "currency": "GBP",
        "idempotency_key": idempotency_key or str(uuid.uuid4()),
        "customer_id": "cust-test-001",
        "reference": "Test payment",
        "debtor_account": {
            "sort_code": "040004",
            "account_number": "00012345",
            "holder_name": "Banxe Ltd",
        },
        "creditor_account": {
            "sort_code": "204514",
            "account_number": "57312354",
            "holder_name": "Alice Smith",
        },
    }


@pytest.fixture(autouse=True)
def fresh_payment_service():
    svc = MockPaymentAdapter(failure_rate=0.0)  # no random failures in tests
    app.dependency_overrides[get_payment_service] = lambda: svc
    yield svc
    app.dependency_overrides.clear()


def test_initiate_fps_returns_201():
    resp = client.post("/v1/payments", json=_fps_payload())
    assert resp.status_code == 201


def test_initiate_payment_returns_id():
    key = str(uuid.uuid4())
    resp = client.post("/v1/payments", json=_fps_payload(key))
    assert resp.json()["payment_id"] == key


def test_initiate_payment_rail():
    resp = client.post("/v1/payments", json=_fps_payload())
    assert resp.json()["rail"] == "FPS"


def test_initiate_payment_amount_string():
    resp = client.post("/v1/payments", json=_fps_payload())
    assert resp.json()["amount"] == "100.00"


def test_initiate_payment_currency():
    resp = client.post("/v1/payments", json=_fps_payload())
    assert resp.json()["currency"] == "GBP"


def test_initiate_payment_status_not_none():
    resp = client.post("/v1/payments", json=_fps_payload())
    assert resp.json()["status"] is not None


def test_amount_float_rejected():
    payload = {**_fps_payload(), "amount": "100.005"}  # > 2dp
    resp = client.post("/v1/payments", json=payload)
    assert resp.status_code == 422


def test_amount_non_numeric_rejected():
    payload = {**_fps_payload(), "amount": "abc"}
    resp = client.post("/v1/payments", json=payload)
    assert resp.status_code == 422


def test_fps_eur_currency_rejected():
    payload = {**_fps_payload(), "currency": "EUR"}
    resp = client.post("/v1/payments", json=payload)
    # FPS only supports GBP — should be 422 due to PaymentIntent validation
    assert resp.status_code == 422


def test_sepa_gbp_currency_rejected():
    payload = {**_fps_payload(), "rail": "SEPA_CT", "currency": "GBP"}
    resp = client.post("/v1/payments", json=payload)
    assert resp.status_code == 422


def test_list_payments_empty_initially():
    resp = client.get("/v1/payments")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_payments_after_initiate():
    client.post("/v1/payments", json=_fps_payload())
    resp = client.get("/v1/payments")
    assert len(resp.json()) == 1


def test_idempotency_same_key_same_result():
    key = str(uuid.uuid4())
    r1 = client.post("/v1/payments", json=_fps_payload(key))
    r2 = client.post("/v1/payments", json=_fps_payload(key))
    assert r1.json()["payment_id"] == r2.json()["payment_id"]


def test_get_payment_returns_200():
    key = str(uuid.uuid4())
    client.post("/v1/payments", json=_fps_payload(key))
    resp = client.get(f"/v1/payments/{key}")
    assert resp.status_code == 200


def test_missing_reference_returns_422():
    payload = {k: v for k, v in _fps_payload().items() if k != "reference"}
    resp = client.post("/v1/payments", json=payload)
    assert resp.status_code == 422


def test_sepa_eur_accepted():
    payload = {
        **_fps_payload(),
        "rail": "SEPA_CT",
        "currency": "EUR",
        "debtor_account": {
            "iban": "GB29NWBK60161331926819",
            "bic": "NWBKGB2L",
            "holder_name": "Banxe Ltd",
        },
        "creditor_account": {
            "iban": "DE89370400440532013000",
            "bic": "COBADEFFXXX",
            "holder_name": "Hans Müller",
        },
    }
    resp = client.post("/v1/payments", json=payload)
    assert resp.status_code == 201
