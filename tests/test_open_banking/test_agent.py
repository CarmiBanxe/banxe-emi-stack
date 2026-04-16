"""
tests/test_open_banking/test_agent.py
IL-OBK-01 | Phase 15 — OpenBankingAgent tests.
"""

from __future__ import annotations

import pytest

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


def _make_agent():
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
    agent = OpenBankingAgent(
        consent_manager=mgr,
        pisp_service=pisp,
        aisp_service=aisp,
        sca_orchestrator=sca,
        token_manager=token_mgr,
        registry=registry,
        audit=audit,
    )
    return agent


# ── create_consent ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_consent_returns_dict_with_id_and_status():
    agent = _make_agent()
    result = await agent.create_consent(
        entity_id="ent-1",
        aspsp_id="barclays-uk",
        consent_type_str="AISP",
        permissions_str=["ACCOUNTS"],
        actor="test",
    )
    assert "id" in result
    assert "status" in result
    assert result["status"] == "AWAITING_AUTHORISATION"


@pytest.mark.asyncio
async def test_create_consent_aspsp_not_found_raises():
    agent = _make_agent()
    with pytest.raises(ValueError, match="ASPSP not found"):
        await agent.create_consent(
            entity_id="ent-1",
            aspsp_id="ghost-bank",
            consent_type_str="AISP",
            permissions_str=["ACCOUNTS"],
            actor="test",
        )


# ── authorise_consent ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_authorise_consent_success():
    agent = _make_agent()
    c = await agent.create_consent(
        entity_id="ent-1",
        aspsp_id="barclays-uk",
        consent_type_str="AISP",
        permissions_str=["ACCOUNTS"],
        actor="test",
    )
    result = await agent.authorise_consent(c["id"], "CODE", "test")
    assert result["status"] == "AUTHORISED"


# ── revoke_consent ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_revoke_consent_success():
    agent = _make_agent()
    c = await agent.create_consent(
        entity_id="ent-1",
        aspsp_id="barclays-uk",
        consent_type_str="AISP",
        permissions_str=["ACCOUNTS"],
        actor="test",
    )
    result = await agent.revoke_consent(c["id"], "test")
    assert result["status"] == "REVOKED"


# ── initiate_payment ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_initiate_payment_returns_dict_with_status():
    agent = _make_agent()
    c = await agent.create_consent(
        entity_id="ent-1",
        aspsp_id="barclays-uk",
        consent_type_str="PISP",
        permissions_str=["ACCOUNTS"],
        actor="test",
    )
    await agent.authorise_consent(c["id"], "CODE", "test")
    result = await agent.initiate_payment(
        consent_id=c["id"],
        entity_id="ent-1",
        aspsp_id="barclays-uk",
        amount_str="100.00",
        currency="GBP",
        creditor_iban="GB29NWBK60161331926819",
        creditor_name="Test Creditor",
        actor="test",
    )
    assert "status" in result
    assert result["status"] == "ACCEPTED"


@pytest.mark.asyncio
async def test_initiate_payment_amount_as_decimal_string():
    agent = _make_agent()
    c = await agent.create_consent(
        entity_id="ent-1",
        aspsp_id="barclays-uk",
        consent_type_str="PISP",
        permissions_str=["ACCOUNTS"],
        actor="test",
    )
    await agent.authorise_consent(c["id"], "CODE", "test")
    result = await agent.initiate_payment(
        consent_id=c["id"],
        entity_id="ent-1",
        aspsp_id="barclays-uk",
        amount_str="100.00",
        currency="GBP",
        creditor_iban="GB29NWBK60161331926819",
        creditor_name="Test Creditor",
        actor="test",
    )
    # Amount in response should be string (Decimal serialised to str)
    assert result["amount"] == "100.00"


# ── get_accounts ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_accounts_returns_list():
    agent = _make_agent()
    c = await agent.create_consent(
        entity_id="ent-1",
        aspsp_id="barclays-uk",
        consent_type_str="AISP",
        permissions_str=["ACCOUNTS", "BALANCES", "TRANSACTIONS"],
        actor="test",
    )
    await agent.authorise_consent(c["id"], "CODE", "test")
    accounts = await agent.get_accounts(c["id"], actor="test")
    assert isinstance(accounts, list)
    assert len(accounts) == 1


# ── get_transactions ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_transactions_success():
    agent = _make_agent()
    c = await agent.create_consent(
        entity_id="ent-1",
        aspsp_id="barclays-uk",
        consent_type_str="AISP",
        permissions_str=["ACCOUNTS", "BALANCES", "TRANSACTIONS"],
        actor="test",
    )
    await agent.authorise_consent(c["id"], "CODE", "test")
    accounts = await agent.get_accounts(c["id"], actor="test")
    txns = await agent.get_transactions(c["id"], accounts[0]["account_id"], actor="test")
    assert isinstance(txns, list)
    assert len(txns) == 1


# ── initiate_sca ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_initiate_sca_returns_dict_with_id_and_flow_type():
    agent = _make_agent()
    c = await agent.create_consent(
        entity_id="ent-1",
        aspsp_id="barclays-uk",
        consent_type_str="AISP",
        permissions_str=["ACCOUNTS"],
        actor="test",
    )
    result = await agent.initiate_sca(c["id"], "REDIRECT", "test")
    assert "id" in result
    assert result["flow_type"] == "REDIRECT"
    assert result["redirect_url"] is not None


# ── list_aspsps ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_aspsps_returns_three():
    agent = _make_agent()
    aspsps = await agent.list_aspsps()
    assert len(aspsps) == 3


# ── get_audit_log ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_audit_log_returns_list_with_event_type():
    agent = _make_agent()
    await agent.create_consent(
        entity_id="ent-1",
        aspsp_id="barclays-uk",
        consent_type_str="AISP",
        permissions_str=["ACCOUNTS"],
        actor="test",
    )
    log = await agent.get_audit_log()
    assert len(log) >= 1
    assert "event_type" in log[0]


@pytest.mark.asyncio
async def test_get_audit_log_filter_by_entity_id():
    agent = _make_agent()
    await agent.create_consent(
        entity_id="ent-A",
        aspsp_id="barclays-uk",
        consent_type_str="AISP",
        permissions_str=["ACCOUNTS"],
        actor="test",
    )
    await agent.create_consent(
        entity_id="ent-B",
        aspsp_id="barclays-uk",
        consent_type_str="AISP",
        permissions_str=["ACCOUNTS"],
        actor="test",
    )
    log_a = await agent.get_audit_log(entity_id="ent-A")
    assert all(e["entity_id"] == "ent-A" for e in log_a)


@pytest.mark.asyncio
async def test_get_audit_log_filter_by_event_type():
    agent = _make_agent()
    c = await agent.create_consent(
        entity_id="ent-1",
        aspsp_id="barclays-uk",
        consent_type_str="AISP",
        permissions_str=["ACCOUNTS"],
        actor="test",
    )
    await agent.authorise_consent(c["id"], "CODE", "test")
    log = await agent.get_audit_log(event_type="consent.authorised")
    assert all(e["event_type"] == "consent.authorised" for e in log)
    assert len(log) == 1


# ── create_consent with PISP ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_consent_pisp_type():
    agent = _make_agent()
    result = await agent.create_consent(
        entity_id="ent-1",
        aspsp_id="barclays-uk",
        consent_type_str="PISP",
        permissions_str=["ACCOUNTS"],
        actor="test",
    )
    assert result["type"] == "PISP"


# ── Full consent lifecycle via agent ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_consent_lifecycle_via_agent():
    agent = _make_agent()
    c = await agent.create_consent(
        entity_id="ent-1",
        aspsp_id="barclays-uk",
        consent_type_str="AISP",
        permissions_str=["ACCOUNTS"],
        actor="test",
    )
    assert c["status"] == "AWAITING_AUTHORISATION"

    auth = await agent.authorise_consent(c["id"], "CODE", "test")
    assert auth["status"] == "AUTHORISED"

    rev = await agent.revoke_consent(c["id"], "test")
    assert rev["status"] == "REVOKED"


# ── create_consent with AISP permissions list ─────────────────────────────────


@pytest.mark.asyncio
async def test_create_consent_aisp_permissions_list():
    agent = _make_agent()
    result = await agent.create_consent(
        entity_id="ent-1",
        aspsp_id="barclays-uk",
        consent_type_str="AISP",
        permissions_str=["ACCOUNTS", "BALANCES", "TRANSACTIONS", "BENEFICIARIES"],
        actor="test",
    )
    assert len(result["permissions"]) == 4
