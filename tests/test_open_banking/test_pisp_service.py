"""
tests/test_open_banking/test_pisp_service.py
IL-OBK-01 | Phase 15 — PISPService tests.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.open_banking.consent_manager import ConsentManager
from services.open_banking.models import (
    AccountAccessType,
    ConsentType,
    InMemoryASPSPRegistry,
    InMemoryConsentStore,
    InMemoryOBAuditTrail,
    InMemoryPaymentGateway,
    PaymentStatus,
)
from services.open_banking.pisp_service import PISPService


def _make_pisp(
    gateway=None,
    audit=None,
    store=None,
    registry=None,
):
    store = store or InMemoryConsentStore()
    registry = registry or InMemoryASPSPRegistry()
    audit = audit or InMemoryOBAuditTrail()
    gateway = gateway or InMemoryPaymentGateway(should_accept=True)
    mgr = ConsentManager(store=store, registry=registry, audit=audit)
    return PISPService(consent_manager=mgr, gateway=gateway, audit=audit), mgr, audit


async def _make_pisp_consent(mgr: ConsentManager) -> str:
    c = await mgr.create_consent(
        "ent-1", "barclays-uk", ConsentType.PISP, [AccountAccessType.ACCOUNTS], actor="test"
    )
    await mgr.authorise_consent(c.id, "CODE", "test")
    return c.id


# ── initiate_payment ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_initiate_payment_success_accepted():
    pisp, mgr, _ = _make_pisp()
    consent_id = await _make_pisp_consent(mgr)
    payment = await pisp.initiate_payment(
        consent_id=consent_id,
        entity_id="ent-1",
        aspsp_id="barclays-uk",
        amount=Decimal("50.00"),
        currency="GBP",
        creditor_iban="GB29NWBK60161331926819",
        creditor_name="Test Creditor",
        actor="test",
    )
    assert payment.status == PaymentStatus.ACCEPTED


@pytest.mark.asyncio
async def test_initiate_payment_creates_audit_entry():
    pisp, mgr, audit = _make_pisp()
    consent_id = await _make_pisp_consent(mgr)
    await pisp.initiate_payment(
        consent_id=consent_id,
        entity_id="ent-1",
        aspsp_id="barclays-uk",
        amount=Decimal("50.00"),
        currency="GBP",
        creditor_iban="GB29NWBK60161331926819",
        creditor_name="Test Creditor",
        actor="test",
    )
    events = await audit.list_events(event_type="payment.initiated")
    assert len(events) == 1


@pytest.mark.asyncio
async def test_initiate_payment_consent_not_found():
    pisp, _, _ = _make_pisp()
    with pytest.raises(ValueError, match="Consent not found"):
        await pisp.initiate_payment(
            consent_id="no-such-consent",
            entity_id="ent-1",
            aspsp_id="barclays-uk",
            amount=Decimal("50.00"),
            currency="GBP",
            creditor_iban="GB29NWBK60161331926819",
            creditor_name="Test Creditor",
            actor="test",
        )


@pytest.mark.asyncio
async def test_initiate_payment_consent_not_authorised():
    pisp, mgr, _ = _make_pisp()
    c = await mgr.create_consent(
        "ent-1", "barclays-uk", ConsentType.PISP, [AccountAccessType.ACCOUNTS], actor="test"
    )
    with pytest.raises(ValueError, match="not authorised"):
        await pisp.initiate_payment(
            consent_id=c.id,
            entity_id="ent-1",
            aspsp_id="barclays-uk",
            amount=Decimal("50.00"),
            currency="GBP",
            creditor_iban="GB29NWBK60161331926819",
            creditor_name="Test Creditor",
            actor="test",
        )


@pytest.mark.asyncio
async def test_initiate_payment_gateway_rejection_still_logs():
    gw = InMemoryPaymentGateway(should_accept=False)
    pisp, mgr, audit = _make_pisp(gateway=gw)
    consent_id = await _make_pisp_consent(mgr)
    with pytest.raises(ValueError):
        await pisp.initiate_payment(
            consent_id=consent_id,
            entity_id="ent-1",
            aspsp_id="barclays-uk",
            amount=Decimal("50.00"),
            currency="GBP",
            creditor_iban="GB29NWBK60161331926819",
            creditor_name="Test Creditor",
            actor="test",
        )
    events = await audit.list_events(event_type="payment.initiated")
    assert len(events) == 1


@pytest.mark.asyncio
async def test_initiate_payment_amount_is_decimal():
    pisp, mgr, _ = _make_pisp()
    consent_id = await _make_pisp_consent(mgr)
    payment = await pisp.initiate_payment(
        consent_id=consent_id,
        entity_id="ent-1",
        aspsp_id="barclays-uk",
        amount=Decimal("99.99"),
        currency="GBP",
        creditor_iban="GB29NWBK60161331926819",
        creditor_name="Test Creditor",
        actor="test",
    )
    assert isinstance(payment.amount, Decimal)
    assert payment.amount == Decimal("99.99")


@pytest.mark.asyncio
async def test_initiate_payment_end_to_end_id_set():
    pisp, mgr, _ = _make_pisp()
    consent_id = await _make_pisp_consent(mgr)
    payment = await pisp.initiate_payment(
        consent_id=consent_id,
        entity_id="ent-1",
        aspsp_id="barclays-uk",
        amount=Decimal("10.00"),
        currency="GBP",
        creditor_iban="GB29NWBK60161331926819",
        creditor_name="Test Creditor",
        actor="test",
    )
    assert payment.end_to_end_id is not None and len(payment.end_to_end_id) > 0


@pytest.mark.asyncio
async def test_initiate_payment_aspsp_payment_id_stored():
    pisp, mgr, _ = _make_pisp()
    consent_id = await _make_pisp_consent(mgr)
    payment = await pisp.initiate_payment(
        consent_id=consent_id,
        entity_id="ent-1",
        aspsp_id="barclays-uk",
        amount=Decimal("10.00"),
        currency="GBP",
        creditor_iban="GB29NWBK60161331926819",
        creditor_name="Test Creditor",
        actor="test",
    )
    assert payment.aspsp_payment_id is not None


@pytest.mark.asyncio
async def test_get_payment_status_returns_accepted():
    pisp, mgr, _ = _make_pisp()
    consent_id = await _make_pisp_consent(mgr)
    payment = await pisp.initiate_payment(
        consent_id=consent_id,
        entity_id="ent-1",
        aspsp_id="barclays-uk",
        amount=Decimal("25.00"),
        currency="GBP",
        creditor_iban="GB29NWBK60161331926819",
        creditor_name="Test Creditor",
        actor="test",
    )
    status = await pisp.get_payment_status(payment)
    assert status == PaymentStatus.ACCEPTED


# ── create_bulk_payment ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_bulk_payment_two_payments():
    pisp, mgr, _ = _make_pisp()
    consent_id = await _make_pisp_consent(mgr)
    payments_spec = [
        {
            "amount": "10.00",
            "currency": "GBP",
            "creditor_iban": "GB29NWBK60161331926819",
            "creditor_name": "Alice",
        },
        {
            "amount": "20.00",
            "currency": "GBP",
            "creditor_iban": "GB29NWBK60161331926820",
            "creditor_name": "Bob",
        },
    ]
    results = await pisp.create_bulk_payment(
        consent_id, "ent-1", "barclays-uk", payments_spec, "test"
    )
    assert len(results) == 2
    for p in results:
        assert p.status == PaymentStatus.ACCEPTED


@pytest.mark.asyncio
async def test_create_bulk_payment_empty_list():
    pisp, mgr, _ = _make_pisp()
    consent_id = await _make_pisp_consent(mgr)
    results = await pisp.create_bulk_payment(consent_id, "ent-1", "barclays-uk", [], "test")
    assert results == []


# ── edge cases ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_initiate_payment_aisp_consent_raises():
    pisp, mgr, _ = _make_pisp()
    c = await mgr.create_consent(
        "ent-1", "barclays-uk", ConsentType.AISP, [AccountAccessType.ACCOUNTS], actor="test"
    )
    await mgr.authorise_consent(c.id, "CODE", "test")
    with pytest.raises(ValueError, match="not a PISP consent"):
        await pisp.initiate_payment(
            consent_id=c.id,
            entity_id="ent-1",
            aspsp_id="barclays-uk",
            amount=Decimal("10.00"),
            currency="GBP",
            creditor_iban="GB29NWBK60161331926819",
            creditor_name="Creditor",
            actor="test",
        )


@pytest.mark.asyncio
async def test_initiate_payment_different_currencies():
    pisp, mgr, _ = _make_pisp()
    consent_id = await _make_pisp_consent(mgr)
    p = await pisp.initiate_payment(
        consent_id=consent_id,
        entity_id="ent-1",
        aspsp_id="barclays-uk",
        amount=Decimal("100.00"),
        currency="EUR",
        creditor_iban="FR1420041010050500013M02606",
        creditor_name="EU Creditor",
        actor="test",
    )
    assert p.currency == "EUR"


@pytest.mark.asyncio
async def test_initiate_payment_debtor_iban_none():
    pisp, mgr, _ = _make_pisp()
    consent_id = await _make_pisp_consent(mgr)
    p = await pisp.initiate_payment(
        consent_id=consent_id,
        entity_id="ent-1",
        aspsp_id="barclays-uk",
        amount=Decimal("10.00"),
        currency="GBP",
        creditor_iban="GB29NWBK60161331926819",
        creditor_name="Creditor",
        actor="test",
        debtor_iban=None,
    )
    assert p.debtor_iban is None


@pytest.mark.asyncio
async def test_initiate_payment_reference_stored():
    pisp, mgr, _ = _make_pisp()
    consent_id = await _make_pisp_consent(mgr)
    p = await pisp.initiate_payment(
        consent_id=consent_id,
        entity_id="ent-1",
        aspsp_id="barclays-uk",
        amount=Decimal("10.00"),
        currency="GBP",
        creditor_iban="GB29NWBK60161331926819",
        creditor_name="Creditor",
        actor="test",
        reference="INVOICE-42",
    )
    assert p.reference == "INVOICE-42"


@pytest.mark.asyncio
async def test_multiple_payments_same_consent():
    pisp, mgr, audit = _make_pisp()
    consent_id = await _make_pisp_consent(mgr)
    for _ in range(3):
        await pisp.initiate_payment(
            consent_id=consent_id,
            entity_id="ent-1",
            aspsp_id="barclays-uk",
            amount=Decimal("5.00"),
            currency="GBP",
            creditor_iban="GB29NWBK60161331926819",
            creditor_name="Creditor",
            actor="test",
        )
    events = await audit.list_events(event_type="payment.initiated")
    assert len(events) == 3
