"""
tests/test_open_banking/test_aisp_service.py
IL-OBK-01 | Phase 15 — AISPService tests.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.open_banking.aisp_service import AISPService
from services.open_banking.consent_manager import ConsentManager
from services.open_banking.models import (
    AccountAccessType,
    ConsentType,
    InMemoryAccountData,
    InMemoryASPSPRegistry,
    InMemoryConsentStore,
    InMemoryOBAuditTrail,
)


def _make_aisp(audit=None):
    store = InMemoryConsentStore()
    registry = InMemoryASPSPRegistry()
    audit = audit or InMemoryOBAuditTrail()
    account_data = InMemoryAccountData()
    mgr = ConsentManager(store=store, registry=registry, audit=audit)
    svc = AISPService(consent_manager=mgr, account_data=account_data, audit=audit)
    return svc, mgr, audit


async def _make_aisp_consent(mgr, permissions=None):
    if permissions is None:
        permissions = [
            AccountAccessType.ACCOUNTS,
            AccountAccessType.BALANCES,
            AccountAccessType.TRANSACTIONS,
        ]
    c = await mgr.create_consent(
        "ent-1", "barclays-uk", ConsentType.AISP, permissions, actor="test"
    )
    await mgr.authorise_consent(c.id, "CODE", "test")
    return c.id


# ── get_accounts ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_accounts_success():
    svc, mgr, _ = _make_aisp()
    consent_id = await _make_aisp_consent(mgr)
    accounts = await svc.get_accounts(consent_id, actor="test")
    assert len(accounts) == 1


@pytest.mark.asyncio
async def test_get_accounts_creates_audit_entry():
    audit = InMemoryOBAuditTrail()
    svc, mgr, _ = _make_aisp(audit=audit)
    consent_id = await _make_aisp_consent(mgr)
    await svc.get_accounts(consent_id, actor="test")
    events = await audit.list_events(event_type="aisp.accounts_fetched")
    assert len(events) == 1


@pytest.mark.asyncio
async def test_get_accounts_awaiting_raises():
    svc, mgr, _ = _make_aisp()
    c = await mgr.create_consent(
        "ent-1", "barclays-uk", ConsentType.AISP, [AccountAccessType.ACCOUNTS], actor="test"
    )
    with pytest.raises(ValueError, match="not authorised"):
        await svc.get_accounts(c.id, actor="test")


@pytest.mark.asyncio
async def test_get_accounts_consent_not_found():
    svc, _, _ = _make_aisp()
    with pytest.raises(ValueError, match="Consent not found"):
        await svc.get_accounts("ghost-id", actor="test")


# ── get_balance ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_balance_success_returns_decimal():
    svc, mgr, _ = _make_aisp()
    consent_id = await _make_aisp_consent(mgr)
    accounts = await svc.get_accounts(consent_id, actor="test")
    balance = await svc.get_balance(consent_id, accounts[0].account_id, actor="test")
    assert isinstance(balance, Decimal)
    assert balance == Decimal("1234.56")


@pytest.mark.asyncio
async def test_get_balance_is_decimal_not_float():
    svc, mgr, _ = _make_aisp()
    consent_id = await _make_aisp_consent(mgr)
    accounts = await svc.get_accounts(consent_id, actor="test")
    balance = await svc.get_balance(consent_id, accounts[0].account_id, actor="test")
    assert not isinstance(balance, float)


@pytest.mark.asyncio
async def test_get_balance_awaiting_raises():
    svc, mgr, _ = _make_aisp()
    c = await mgr.create_consent(
        "ent-1",
        "barclays-uk",
        ConsentType.AISP,
        [AccountAccessType.ACCOUNTS, AccountAccessType.BALANCES],
        actor="test",
    )
    with pytest.raises(ValueError, match="not authorised"):
        await svc.get_balance(c.id, "acc-001", actor="test")


@pytest.mark.asyncio
async def test_get_balance_for_specific_account():
    svc, mgr, _ = _make_aisp()
    consent_id = await _make_aisp_consent(mgr)
    accounts = await svc.get_accounts(consent_id, actor="test")
    account_id = accounts[0].account_id
    balance = await svc.get_balance(consent_id, account_id, actor="test")
    assert balance > Decimal("0")


# ── get_transactions ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_transactions_success():
    svc, mgr, _ = _make_aisp()
    consent_id = await _make_aisp_consent(mgr)
    accounts = await svc.get_accounts(consent_id, actor="test")
    txns = await svc.get_transactions(consent_id, accounts[0].account_id, actor="test")
    assert len(txns) == 1


@pytest.mark.asyncio
async def test_get_transactions_creates_audit_entry():
    audit = InMemoryOBAuditTrail()
    svc, mgr, _ = _make_aisp(audit=audit)
    consent_id = await _make_aisp_consent(mgr)
    accounts = await svc.get_accounts(consent_id, actor="test")
    await svc.get_transactions(consent_id, accounts[0].account_id, actor="test")
    events = await audit.list_events(event_type="aisp.transactions_fetched")
    assert len(events) == 1


@pytest.mark.asyncio
async def test_get_transactions_awaiting_raises():
    svc, mgr, _ = _make_aisp()
    c = await mgr.create_consent(
        "ent-1",
        "barclays-uk",
        ConsentType.AISP,
        [AccountAccessType.ACCOUNTS, AccountAccessType.TRANSACTIONS],
        actor="test",
    )
    with pytest.raises(ValueError, match="not authorised"):
        await svc.get_transactions(c.id, "acc-001", actor="test")


# ── PISP consent for AISP operations ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_pisp_consent_used_for_aisp_raises():
    svc, mgr, _ = _make_aisp()
    c = await mgr.create_consent(
        "ent-1", "barclays-uk", ConsentType.PISP, [AccountAccessType.ACCOUNTS], actor="test"
    )
    await mgr.authorise_consent(c.id, "CODE", "test")
    with pytest.raises(ValueError, match="not an AISP consent"):
        await svc.get_accounts(c.id, actor="test")


# ── Transaction amounts are Decimal ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_transaction_amounts_are_decimal():
    svc, mgr, _ = _make_aisp()
    consent_id = await _make_aisp_consent(mgr)
    accounts = await svc.get_accounts(consent_id, actor="test")
    txns = await svc.get_transactions(consent_id, accounts[0].account_id, actor="test")
    for txn in txns:
        assert isinstance(txn.amount, Decimal)
        assert not isinstance(txn.amount, float)


# ── Multiple accounts ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_accounts_returns_account_info_object():
    svc, mgr, _ = _make_aisp()
    consent_id = await _make_aisp_consent(mgr)
    accounts = await svc.get_accounts(consent_id, actor="test")
    assert accounts[0].iban is not None
    assert accounts[0].currency == "GBP"
