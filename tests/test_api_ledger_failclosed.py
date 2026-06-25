"""
tests/test_api_ledger_failclosed.py — ledger API fail-closed mapping.

Production branch (non-sandbox) of api/routers/ledger.py: a
LedgerInfrastructureError from midaz_client (Midaz unreachable / 5xx) maps to
HTTP 503 — never a silent 200/zero. A reachable "not found" (None) stays 404.

Offline — no live Midaz; a fake midaz_client module is injected and
`_is_sandbox` is forced False.
"""

from __future__ import annotations

from decimal import Decimal
import sys
import types

from fastapi.testclient import TestClient
import pytest

from api.main import app
from services.ledger.ledger_port import LedgerInfrastructureError

client = TestClient(app)


def _fake_midaz(*, balance=None, accounts=None, raise_infra=False) -> types.ModuleType:
    mod = types.ModuleType("services.ledger.midaz_client")

    async def get_balance(account_id: str):
        if raise_infra:
            raise LedgerInfrastructureError("Midaz down")
        return balance

    async def list_accounts():
        if raise_infra:
            raise LedgerInfrastructureError("Midaz down")
        return accounts or []

    mod.get_balance = get_balance  # type: ignore[attr-defined]
    mod.list_accounts = list_accounts  # type: ignore[attr-defined]
    return mod


@pytest.fixture
def production(monkeypatch):
    """Force the production (non-sandbox) router branch."""
    monkeypatch.setattr("api.routers.ledger._is_sandbox", lambda: False)
    return monkeypatch


def _inject(production, module: types.ModuleType) -> None:
    production.setitem(sys.modules, "services.ledger.midaz_client", module)


def test_balance_infra_error_returns_503(production):
    _inject(production, _fake_midaz(raise_infra=True))
    resp = client.get("/v1/ledger/accounts/acc-x/balance")
    assert resp.status_code == 503


def test_balance_unknown_account_returns_404(production):
    _inject(production, _fake_midaz(balance=None))
    resp = client.get("/v1/ledger/accounts/acc-x/balance")
    assert resp.status_code == 404


def test_balance_production_happy_200(production):
    _inject(production, _fake_midaz(balance=Decimal("123.45")))
    resp = client.get("/v1/ledger/accounts/acc-x/balance")
    assert resp.status_code == 200
    assert resp.json()["available"] == "123.45"


def test_list_accounts_infra_error_returns_503(production):
    _inject(production, _fake_midaz(raise_infra=True))
    resp = client.get("/v1/ledger/accounts")
    assert resp.status_code == 503


def test_list_accounts_production_happy_200(production):
    accts = [
        {"id": "a1", "name": "A", "type": "OPERATIONAL", "assetCode": "GBP", "status": "ACTIVE"}
    ]
    _inject(production, _fake_midaz(accounts=accts))
    resp = client.get("/v1/ledger/accounts")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
