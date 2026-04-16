"""
tests/test_merchant_acquiring/test_payment_gateway.py
IL-MAG-01 | Phase 20 — Payment gateway service tests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.merchant_acquiring.merchant_onboarding import MerchantOnboarding
from services.merchant_acquiring.models import (
    InMemoryMAAudit,
    InMemoryMerchantStore,
    InMemoryPaymentStore,
    PaymentResult,
)
from services.merchant_acquiring.payment_gateway import PaymentGateway

_NOW = datetime.now(UTC)


def _make_gateway() -> tuple[PaymentGateway, InMemoryMerchantStore, InMemoryMAAudit]:
    merchant_store = InMemoryMerchantStore()
    payment_store = InMemoryPaymentStore()
    audit = InMemoryMAAudit()
    gw = PaymentGateway(merchant_store, payment_store, audit)
    return gw, merchant_store, audit


async def _create_active_merchant(store: InMemoryMerchantStore) -> str:
    audit = InMemoryMAAudit()
    onboarding = MerchantOnboarding(store, audit)
    m = await onboarding.onboard("Shop", "Shop Ltd", "5411", "GB", None, "5000", "100000", "admin")
    await onboarding.approve_kyb(m.id, "admin")
    return m.id


@pytest.mark.asyncio
async def test_accept_payment_approved_for_small_amount() -> None:
    gw, store, _ = _make_gateway()
    mid = await _create_active_merchant(store)
    p = await gw.accept_payment(mid, "20.00", "GBP", "4242", "ref-001", "admin")
    assert p.result == PaymentResult.APPROVED
    assert p.requires_3ds is False


@pytest.mark.asyncio
async def test_accept_payment_pending_3ds_for_large_amount() -> None:
    gw, store, _ = _make_gateway()
    mid = await _create_active_merchant(store)
    p = await gw.accept_payment(mid, "50.00", "GBP", "4242", "ref-001", "admin")
    assert p.result == PaymentResult.PENDING_3DS
    assert p.requires_3ds is True


@pytest.mark.asyncio
async def test_accept_payment_non_active_merchant_raises_value_error() -> None:
    gw, store, _ = _make_gateway()
    # Onboard but don't approve KYB — merchant is PENDING_KYB
    audit = InMemoryMAAudit()
    onboarding = MerchantOnboarding(store, audit)
    m = await onboarding.onboard("Shop", "Shop Ltd", "5411", "GB", None, "5000", "100000", "admin")
    with pytest.raises(ValueError):
        await gw.accept_payment(m.id, "20.00", "GBP", "4242", "ref", "admin")


@pytest.mark.asyncio
async def test_accept_payment_creates_audit_event() -> None:
    gw, store, audit = _make_gateway()
    mid = await _create_active_merchant(store)
    p = await gw.accept_payment(mid, "20.00", "GBP", "4242", "ref", "admin")
    events = await audit.list_events(mid)
    assert any(e["event_type"] == "payment.accepted" for e in events)


@pytest.mark.asyncio
async def test_accept_payment_acquirer_ref_is_set() -> None:
    gw, store, _ = _make_gateway()
    mid = await _create_active_merchant(store)
    p = await gw.accept_payment(mid, "20.00", "GBP", "4242", "ref", "admin")
    assert p.acquirer_ref is not None
    assert len(p.acquirer_ref) > 0


@pytest.mark.asyncio
async def test_accept_payment_card_last_four_preserved() -> None:
    gw, store, _ = _make_gateway()
    mid = await _create_active_merchant(store)
    p = await gw.accept_payment(mid, "20.00", "GBP", "9876", "ref", "admin")
    assert p.card_last_four == "9876"


@pytest.mark.asyncio
async def test_complete_3ds_approves_payment() -> None:
    gw, store, _ = _make_gateway()
    mid = await _create_active_merchant(store)
    p = await gw.accept_payment(mid, "50.00", "GBP", "4242", "ref", "admin")
    assert p.result == PaymentResult.PENDING_3DS
    completed = await gw.complete_3ds(p.id, "admin")
    assert completed.result == PaymentResult.APPROVED


@pytest.mark.asyncio
async def test_complete_3ds_already_approved_raises_value_error() -> None:
    gw, store, _ = _make_gateway()
    mid = await _create_active_merchant(store)
    p = await gw.accept_payment(mid, "20.00", "GBP", "4242", "ref", "admin")
    assert p.result == PaymentResult.APPROVED
    with pytest.raises(ValueError):
        await gw.complete_3ds(p.id, "admin")


@pytest.mark.asyncio
async def test_complete_3ds_creates_audit_event() -> None:
    gw, store, audit = _make_gateway()
    mid = await _create_active_merchant(store)
    p = await gw.accept_payment(mid, "50.00", "GBP", "4242", "ref", "admin")
    await gw.complete_3ds(p.id, "admin")
    events = await audit.list_events(mid)
    assert any(e["event_type"] == "payment.3ds_completed" for e in events)


@pytest.mark.asyncio
async def test_void_payment_approved_to_declined() -> None:
    gw, store, _ = _make_gateway()
    mid = await _create_active_merchant(store)
    p = await gw.accept_payment(mid, "20.00", "GBP", "4242", "ref", "admin")
    voided = await gw.void_payment(p.id, "admin")
    assert voided.result == PaymentResult.DECLINED


@pytest.mark.asyncio
async def test_void_payment_non_approved_raises_value_error() -> None:
    gw, store, _ = _make_gateway()
    mid = await _create_active_merchant(store)
    p = await gw.accept_payment(mid, "50.00", "GBP", "4242", "ref", "admin")
    assert p.result == PaymentResult.PENDING_3DS
    with pytest.raises(ValueError):
        await gw.void_payment(p.id, "admin")


@pytest.mark.asyncio
async def test_void_payment_creates_audit_event() -> None:
    gw, store, audit = _make_gateway()
    mid = await _create_active_merchant(store)
    p = await gw.accept_payment(mid, "20.00", "GBP", "4242", "ref", "admin")
    await gw.void_payment(p.id, "admin")
    events = await audit.list_events(mid)
    assert any(e["event_type"] == "payment.voided" for e in events)


@pytest.mark.asyncio
async def test_get_payment_existing() -> None:
    gw, store, _ = _make_gateway()
    mid = await _create_active_merchant(store)
    p = await gw.accept_payment(mid, "20.00", "GBP", "4242", "ref", "admin")
    found = await gw.get_payment(p.id)
    assert found is not None
    assert found.id == p.id


@pytest.mark.asyncio
async def test_get_payment_none_for_missing() -> None:
    gw, _, _ = _make_gateway()
    assert await gw.get_payment("no-such-payment") is None


@pytest.mark.asyncio
async def test_list_payments_returns_all_for_merchant() -> None:
    gw, store, _ = _make_gateway()
    mid = await _create_active_merchant(store)
    await gw.accept_payment(mid, "10.00", "GBP", "1111", "r1", "admin")
    await gw.accept_payment(mid, "20.00", "GBP", "2222", "r2", "admin")
    payments = await gw.list_payments(mid)
    assert len(payments) == 2


@pytest.mark.asyncio
async def test_accept_payment_reference_preserved() -> None:
    gw, store, _ = _make_gateway()
    mid = await _create_active_merchant(store)
    p = await gw.accept_payment(mid, "20.00", "GBP", "4242", "my-ref-xyz", "admin")
    assert p.reference == "my-ref-xyz"


@pytest.mark.asyncio
async def test_accept_payment_amount_is_decimal() -> None:
    gw, store, _ = _make_gateway()
    mid = await _create_active_merchant(store)
    p = await gw.accept_payment(mid, "15.50", "GBP", "4242", "ref", "admin")
    assert isinstance(p.amount, Decimal)
    assert p.amount == Decimal("15.50")


@pytest.mark.asyncio
async def test_small_payment_requires_3ds_false() -> None:
    gw, store, _ = _make_gateway()
    mid = await _create_active_merchant(store)
    p = await gw.accept_payment(mid, "5.00", "GBP", "4242", "ref", "admin")
    assert p.requires_3ds is False


@pytest.mark.asyncio
async def test_large_payment_requires_3ds_true() -> None:
    gw, store, _ = _make_gateway()
    mid = await _create_active_merchant(store)
    p = await gw.accept_payment(mid, "100.00", "GBP", "4242", "ref", "admin")
    assert p.requires_3ds is True


@pytest.mark.asyncio
async def test_multiple_payments_for_same_merchant() -> None:
    gw, store, _ = _make_gateway()
    mid = await _create_active_merchant(store)
    for i in range(5):
        await gw.accept_payment(mid, "10.00", "GBP", "4242", f"ref-{i}", "admin")
    payments = await gw.list_payments(mid)
    assert len(payments) == 5
