"""
tests/test_open_banking/test_api_open_banking.py
IL-OBK-01 | Phase 15 — Open Banking API endpoint tests.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from api.main import app
from api.routers.open_banking import _get_agent
from api.routers.open_banking import router as ob_router
from services.open_banking.aisp_service import AISPService
from services.open_banking.consent_manager import ConsentManager
from services.open_banking.models import (
    InMemoryAccountData,
    InMemoryASPSPRegistry,
    InMemoryConsentStore,
    InMemoryOBAuditTrail,
    InMemoryPaymentGateway,
)
from services.open_banking.open_banking_agent import OpenBankingAgent
from services.open_banking.pisp_service import PISPService
from services.open_banking.sca_orchestrator import SCAOrchestrator
from services.open_banking.token_manager import TokenManager


def _fresh_agent() -> OpenBankingAgent:
    store = InMemoryConsentStore()
    registry = InMemoryASPSPRegistry()
    audit = InMemoryOBAuditTrail()
    gateway = InMemoryPaymentGateway(should_accept=True)
    account_data = InMemoryAccountData()
    mgr = ConsentManager(store=store, registry=registry, audit=audit)
    pisp = PISPService(consent_manager=mgr, gateway=gateway, audit=audit)
    aisp = AISPService(consent_manager=mgr, account_data=account_data, audit=audit)
    sca = SCAOrchestrator(consent_manager=mgr, audit=audit)
    token_mgr = TokenManager(registry=registry, audit=audit)
    return OpenBankingAgent(
        consent_manager=mgr,
        pisp_service=pisp,
        aisp_service=aisp,
        sca_orchestrator=sca,
        token_manager=token_mgr,
        registry=registry,
        audit=audit,
    )


@pytest.fixture(scope="module", autouse=True)
def include_ob_router():
    """Include the open-banking router in the test app if not already present."""
    if not any(r is ob_router for r in app.routes):
        app.include_router(ob_router, prefix="/v1")
    yield


@pytest.fixture(autouse=True)
def override_agent():
    """Replace the cached agent with a fresh one per test."""
    agent = _fresh_agent()
    app.dependency_overrides[_get_agent] = lambda: agent
    _get_agent.cache_clear()
    yield agent
    app.dependency_overrides.pop(_get_agent, None)
    _get_agent.cache_clear()


client = TestClient(app)

_CREATE_CONSENT_BODY = {
    "aspsp_id": "barclays-uk",
    "entity_id": "ent-test",
    "consent_type": "AISP",
    "permissions": ["ACCOUNTS", "BALANCES", "TRANSACTIONS"],
    "actor": "test-user",
}

_PAYMENT_CONSENT_BODY = {
    "aspsp_id": "barclays-uk",
    "entity_id": "ent-test",
    "consent_type": "PISP",
    "permissions": ["ACCOUNTS"],
    "actor": "test-user",
}


def _create_consent(body=None) -> str:
    resp = client.post("/v1/open-banking/consents", json=body or _CREATE_CONSENT_BODY)
    assert resp.status_code == 200
    return resp.json()["id"]


def _create_and_authorise_consent(body=None) -> str:
    consent_id = _create_consent(body)
    resp = client.post(
        f"/v1/open-banking/consents/{consent_id}/authorise",
        json={"auth_code": "CODE123", "actor": "test-user"},
    )
    assert resp.status_code == 200
    return consent_id


# ── POST /v1/open-banking/consents ────────────────────────────────────────────


def test_create_consent_returns_200():
    resp = client.post("/v1/open-banking/consents", json=_CREATE_CONSENT_BODY)
    assert resp.status_code == 200


def test_create_consent_aspsp_not_found_returns_422():
    resp = client.post(
        "/v1/open-banking/consents",
        json={**_CREATE_CONSENT_BODY, "aspsp_id": "ghost-bank"},
    )
    assert resp.status_code == 422


# ── GET /v1/open-banking/consents/{id} ────────────────────────────────────────


def test_get_consent_returns_200():
    consent_id = _create_consent()
    resp = client.get(f"/v1/open-banking/consents/{consent_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == consent_id


def test_get_consent_unknown_returns_404():
    resp = client.get("/v1/open-banking/consents/no-such-id")
    assert resp.status_code == 404


# ── POST /v1/open-banking/consents/{id}/authorise ────────────────────────────


def test_authorise_consent_returns_200():
    consent_id = _create_consent()
    resp = client.post(
        f"/v1/open-banking/consents/{consent_id}/authorise",
        json={"auth_code": "CODE123", "actor": "test-user"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "AUTHORISED"


def test_authorise_consent_not_found_returns_422():
    resp = client.post(
        "/v1/open-banking/consents/ghost-id/authorise",
        json={"auth_code": "CODE", "actor": "test"},
    )
    assert resp.status_code == 422


# ── DELETE /v1/open-banking/consents/{id} ────────────────────────────────────


def test_revoke_consent_returns_200():
    consent_id = _create_consent()
    resp = client.delete(f"/v1/open-banking/consents/{consent_id}?actor=test")
    assert resp.status_code == 200
    assert resp.json()["status"] == "REVOKED"


# ── POST /v1/open-banking/payments ───────────────────────────────────────────


def test_initiate_payment_returns_200():
    consent_id = _create_and_authorise_consent(_PAYMENT_CONSENT_BODY)
    resp = client.post(
        "/v1/open-banking/payments",
        json={
            "consent_id": consent_id,
            "entity_id": "ent-test",
            "aspsp_id": "barclays-uk",
            "amount": "100.00",
            "currency": "GBP",
            "creditor_iban": "GB29NWBK60161331926819",
            "creditor_name": "Test Creditor",
            "actor": "test-user",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ACCEPTED"


def test_initiate_payment_consent_not_authorised_returns_422():
    consent_id = _create_consent(_PAYMENT_CONSENT_BODY)
    resp = client.post(
        "/v1/open-banking/payments",
        json={
            "consent_id": consent_id,
            "entity_id": "ent-test",
            "aspsp_id": "barclays-uk",
            "amount": "100.00",
            "currency": "GBP",
            "creditor_iban": "GB29NWBK60161331926819",
            "creditor_name": "Test Creditor",
            "actor": "test-user",
        },
    )
    assert resp.status_code == 422


def test_initiate_payment_amount_field_is_string():
    consent_id = _create_and_authorise_consent(_PAYMENT_CONSENT_BODY)
    resp = client.post(
        "/v1/open-banking/payments",
        json={
            "consent_id": consent_id,
            "entity_id": "ent-test",
            "aspsp_id": "barclays-uk",
            "amount": "250.00",
            "currency": "GBP",
            "creditor_iban": "GB29NWBK60161331926819",
            "creditor_name": "Test Creditor",
            "actor": "test-user",
        },
    )
    assert resp.status_code == 200
    # Amount in response is serialized as a string
    assert resp.json()["amount"] == "250.00"


# ── GET /v1/open-banking/payments/{id}/status ────────────────────────────────


def test_get_payment_status_returns_200():
    resp = client.get("/v1/open-banking/payments/some-payment-id/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert data["payment_id"] == "some-payment-id"


# ── GET /v1/open-banking/accounts ────────────────────────────────────────────


def test_get_accounts_returns_200():
    consent_id = _create_and_authorise_consent()
    resp = client.get(f"/v1/open-banking/accounts?consent_id={consent_id}&actor=test")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) == 1


def test_get_accounts_consent_not_authorised_returns_422():
    consent_id = _create_consent()
    resp = client.get(f"/v1/open-banking/accounts?consent_id={consent_id}")
    assert resp.status_code == 422


# ── GET /v1/open-banking/aspsps ──────────────────────────────────────────────


def test_list_aspsps_returns_200_with_min_3():
    resp = client.get("/v1/open-banking/aspsps")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 3


# ── Audit log populated after operations ─────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_log_populated_after_create_consent(override_agent):
    _create_consent()
    events = await override_agent._audit.list_events(event_type="consent.created")
    assert len(events) >= 1


# ── Parallel consents for same entity ────────────────────────────────────────


def test_parallel_consents_same_entity():
    ids = set()
    for _ in range(3):
        consent_id = _create_consent()
        ids.add(consent_id)
    assert len(ids) == 3
