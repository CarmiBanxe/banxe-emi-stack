"""
tests/test_open_banking/test_models.py
IL-OBK-01 | Phase 15 — domain model and InMemory stub tests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.open_banking.models import (
    ASPSP,
    AccountAccessType,
    AccountInfo,
    ASPSPStandard,
    Consent,
    ConsentStatus,
    ConsentType,
    InMemoryAccountData,
    InMemoryASPSPRegistry,
    InMemoryConsentStore,
    InMemoryOBAuditTrail,
    InMemoryPaymentGateway,
    OBEventEntry,
    PaymentInitiation,
    PaymentStatus,
    Transaction,
)


def _make_consent(**kwargs) -> Consent:
    defaults = {
        "id": "c-001",
        "type": ConsentType.AISP,
        "aspsp_id": "barclays-uk",
        "entity_id": "ent-1",
        "permissions": [AccountAccessType.ACCOUNTS],
        "status": ConsentStatus.AWAITING_AUTHORISATION,
        "created_at": datetime.now(UTC),
        "expires_at": datetime(2027, 1, 1, tzinfo=UTC),
    }
    defaults.update(kwargs)
    return Consent(**defaults)


def _make_payment(**kwargs) -> PaymentInitiation:
    defaults = {
        "id": "pay-1",
        "consent_id": "c-001",
        "entity_id": "ent-1",
        "aspsp_id": "barclays-uk",
        "amount": Decimal("100.00"),
        "currency": "GBP",
        "creditor_iban": "GB29NWBK60161331926819",
        "creditor_name": "Test Creditor",
        "reference": "REF-001",
        "status": PaymentStatus.PENDING,
        "created_at": datetime.now(UTC),
        "end_to_end_id": "e2e-001",
    }
    defaults.update(kwargs)
    return PaymentInitiation(**defaults)


# ── Consent dataclass ─────────────────────────────────────────────────────────


def test_consent_creation():
    c = _make_consent()
    assert c.id == "c-001"
    assert c.type == ConsentType.AISP
    assert c.status == ConsentStatus.AWAITING_AUTHORISATION


def test_consent_is_frozen():
    from dataclasses import FrozenInstanceError

    c = _make_consent()
    with pytest.raises(FrozenInstanceError):
        c.status = ConsentStatus.AUTHORISED  # type: ignore[misc]


def test_consent_optional_fields_default_none():
    c = _make_consent()
    assert c.authorised_at is None
    assert c.redirect_uri is None


def test_consent_with_redirect_uri():
    c = _make_consent(redirect_uri="https://example.com/callback")
    assert c.redirect_uri == "https://example.com/callback"


# ── PaymentInitiation dataclass ───────────────────────────────────────────────


def test_payment_amount_is_decimal():
    p = _make_payment()
    assert isinstance(p.amount, Decimal)
    assert p.amount == Decimal("100.00")


def test_payment_creation():
    p = _make_payment()
    assert p.id == "pay-1"
    assert p.status == PaymentStatus.PENDING


def test_payment_debtor_iban_optional():
    p = _make_payment()
    assert p.debtor_iban is None


def test_payment_is_frozen():
    from dataclasses import FrozenInstanceError

    p = _make_payment()
    with pytest.raises(FrozenInstanceError):
        p.status = PaymentStatus.ACCEPTED  # type: ignore[misc]


# ── ASPSP model ───────────────────────────────────────────────────────────────


def test_aspsp_creation():
    a = ASPSP(
        id="test-bank",
        name="Test Bank",
        country="GB",
        standard=ASPSPStandard.UK_OBIE,
        api_base_url="https://api.testbank.com",
        auth_url="https://auth.testbank.com/authorize",
        token_url="https://auth.testbank.com/token",
        client_id="test-client",
    )
    assert a.id == "test-bank"
    assert a.standard == ASPSPStandard.UK_OBIE


# ── InMemoryConsentStore ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_consent_store_save_and_get():
    store = InMemoryConsentStore()
    c = _make_consent()
    await store.save(c)
    result = await store.get("c-001")
    assert result is not None
    assert result.id == "c-001"


@pytest.mark.asyncio
async def test_consent_store_get_missing_returns_none():
    store = InMemoryConsentStore()
    result = await store.get("unknown")
    assert result is None


@pytest.mark.asyncio
async def test_consent_store_list_by_entity():
    store = InMemoryConsentStore()
    c1 = _make_consent(id="c-1", entity_id="ent-A")
    c2 = _make_consent(id="c-2", entity_id="ent-A")
    c3 = _make_consent(id="c-3", entity_id="ent-B")
    for c in (c1, c2, c3):
        await store.save(c)
    results = await store.list_by_entity("ent-A")
    assert len(results) == 2
    ids = {r.id for r in results}
    assert "c-1" in ids
    assert "c-2" in ids


@pytest.mark.asyncio
async def test_consent_store_update_status():
    store = InMemoryConsentStore()
    c = _make_consent()
    await store.save(c)
    updated = await store.update_status("c-001", ConsentStatus.AUTHORISED)
    assert updated.status == ConsentStatus.AUTHORISED
    stored = await store.get("c-001")
    assert stored.status == ConsentStatus.AUTHORISED  # type: ignore[union-attr]


# ── InMemoryPaymentGateway ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gateway_accept():
    gw = InMemoryPaymentGateway(should_accept=True)
    p = _make_payment()
    aspsp_id = await gw.submit_payment(p)
    assert "pay-1" in aspsp_id


@pytest.mark.asyncio
async def test_gateway_reject():
    gw = InMemoryPaymentGateway(should_accept=False)
    p = _make_payment()
    with pytest.raises(ValueError):
        await gw.submit_payment(p)


@pytest.mark.asyncio
async def test_gateway_get_status():
    gw = InMemoryPaymentGateway()
    status = await gw.get_payment_status("aspsp-pay-abc", "barclays-uk")
    assert status == PaymentStatus.ACCEPTED


# ── InMemoryASPSPRegistry ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aspsp_registry_get_existing():
    reg = InMemoryASPSPRegistry()
    aspsp = await reg.get("barclays-uk")
    assert aspsp is not None
    assert aspsp.country == "GB"


@pytest.mark.asyncio
async def test_aspsp_registry_get_missing():
    reg = InMemoryASPSPRegistry()
    result = await reg.get("nonexistent-bank")
    assert result is None


@pytest.mark.asyncio
async def test_aspsp_registry_list_all_has_three():
    reg = InMemoryASPSPRegistry()
    all_aspsps = await reg.list_all()
    assert len(all_aspsps) == 3


@pytest.mark.asyncio
async def test_aspsp_registry_contains_berlin_group():
    reg = InMemoryASPSPRegistry()
    bnp = await reg.get("bnp-fr")
    assert bnp is not None
    assert bnp.standard == ASPSPStandard.BERLIN_GROUP
    assert bnp.country == "FR"


# ── InMemoryAccountData ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_account_data_get_accounts():
    data = InMemoryAccountData()
    accounts = await data.get_accounts("consent-1", "barclays-uk")
    assert len(accounts) == 1
    assert isinstance(accounts[0], AccountInfo)


@pytest.mark.asyncio
async def test_account_data_get_balance_is_decimal():
    data = InMemoryAccountData()
    balance = await data.get_balance("consent-1", "acc-001", "barclays-uk")
    assert isinstance(balance, Decimal)
    assert balance == Decimal("1234.56")


@pytest.mark.asyncio
async def test_account_data_get_transactions():
    data = InMemoryAccountData()
    txns = await data.get_transactions("consent-1", "acc-001", "barclays-uk")
    assert len(txns) == 1
    assert isinstance(txns[0], Transaction)
    assert isinstance(txns[0].amount, Decimal)


# ── InMemoryOBAuditTrail ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_trail_append_and_list():
    trail = InMemoryOBAuditTrail()
    entry = OBEventEntry(
        id="ev-1",
        event_type="consent.created",
        entity_id="ent-1",
        consent_id="c-001",
        payment_id=None,
        details={},
        created_at=datetime.now(UTC),
        actor="test",
    )
    await trail.append(entry)
    events = await trail.list_events()
    assert len(events) == 1


@pytest.mark.asyncio
async def test_audit_trail_filter_by_entity():
    trail = InMemoryOBAuditTrail()
    for eid, evid in [("ent-A", "ev-1"), ("ent-B", "ev-2"), ("ent-A", "ev-3")]:
        await trail.append(
            OBEventEntry(
                id=evid,
                event_type="test",
                entity_id=eid,
                consent_id=None,
                payment_id=None,
                details={},
                created_at=datetime.now(UTC),
                actor="tester",
            )
        )
    results = await trail.list_events(entity_id="ent-A")
    assert len(results) == 2


@pytest.mark.asyncio
async def test_audit_trail_filter_by_event_type():
    trail = InMemoryOBAuditTrail()
    for ev_type, evid in [("consent.created", "ev-1"), ("payment.initiated", "ev-2")]:
        await trail.append(
            OBEventEntry(
                id=evid,
                event_type=ev_type,
                entity_id="ent-1",
                consent_id=None,
                payment_id=None,
                details={},
                created_at=datetime.now(UTC),
                actor="tester",
            )
        )
    results = await trail.list_events(event_type="consent.created")
    assert len(results) == 1
    assert results[0].event_type == "consent.created"
