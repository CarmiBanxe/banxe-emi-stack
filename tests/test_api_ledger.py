"""
tests/test_api_ledger.py — Ledger API endpoint tests
IL-046 | banxe-emi-stack

Tests run in sandbox mode (MIDAZ_BASE_URL not set → mock data).
"""

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_list_accounts_returns_200():
    resp = client.get("/v1/ledger/accounts")
    assert resp.status_code == 200


def test_list_accounts_has_total():
    resp = client.get("/v1/ledger/accounts")
    assert "total" in resp.json()


def test_list_accounts_has_accounts_list():
    resp = client.get("/v1/ledger/accounts")
    assert isinstance(resp.json()["accounts"], list)


def test_list_accounts_sandbox_returns_two():
    resp = client.get("/v1/ledger/accounts")
    assert resp.json()["total"] == 2


def test_list_accounts_operational_present():
    resp = client.get("/v1/ledger/accounts")
    ids = [a["account_id"] for a in resp.json()["accounts"]]
    assert "acc-operational-001" in ids


def test_list_accounts_safeguarding_present():
    resp = client.get("/v1/ledger/accounts")
    ids = [a["account_id"] for a in resp.json()["accounts"]]
    assert "acc-client-funds-001" in ids


def test_list_accounts_currency_gbp():
    resp = client.get("/v1/ledger/accounts")
    currencies = {a["currency"] for a in resp.json()["accounts"]}
    assert "GBP" in currencies


def test_list_accounts_status_active():
    resp = client.get("/v1/ledger/accounts")
    statuses = {a["status"] for a in resp.json()["accounts"]}
    assert "ACTIVE" in statuses


def test_get_balance_operational_returns_200():
    resp = client.get("/v1/ledger/accounts/acc-operational-001/balance")
    assert resp.status_code == 200


def test_get_balance_operational_available():
    resp = client.get("/v1/ledger/accounts/acc-operational-001/balance")
    data = resp.json()
    assert data["available"] == "4700.00"


def test_get_balance_operational_total():
    resp = client.get("/v1/ledger/accounts/acc-operational-001/balance")
    assert resp.json()["total"] == "4750.00"


def test_get_balance_safeguarding_returns_200():
    resp = client.get("/v1/ledger/accounts/acc-client-funds-001/balance")
    assert resp.status_code == 200


def test_get_balance_safeguarding_amount():
    resp = client.get("/v1/ledger/accounts/acc-client-funds-001/balance")
    assert resp.json()["available"] == "125000.00"


def test_get_balance_not_found_returns_404():
    resp = client.get("/v1/ledger/accounts/nonexistent-account/balance")
    assert resp.status_code == 404


def test_get_balance_amount_is_string_not_float():
    resp = client.get("/v1/ledger/accounts/acc-operational-001/balance")
    available = resp.json()["available"]
    assert isinstance(available, str), "Amount must be string, not float (I-05)"


def test_get_balance_currency_field():
    resp = client.get("/v1/ledger/accounts/acc-operational-001/balance")
    assert resp.json()["currency"] == "GBP"
