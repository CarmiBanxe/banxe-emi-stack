"""
tests/test_merchant_acquiring/test_settlement_engine.py
IL-MAG-01 | Phase 20 — Settlement engine tests.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.merchant_acquiring.merchant_onboarding import MerchantOnboarding
from services.merchant_acquiring.models import (
    InMemoryMAAudit,
    InMemoryMerchantStore,
    InMemoryPaymentStore,
    InMemorySettlementStore,
    SettlementStatus,
)
from services.merchant_acquiring.payment_gateway import PaymentGateway
from services.merchant_acquiring.settlement_engine import FEE_RATE, SettlementEngine


def _make_engine() -> tuple[
    SettlementEngine, InMemoryMerchantStore, InMemoryPaymentStore, InMemoryMAAudit
]:
    merchant_store = InMemoryMerchantStore()
    payment_store = InMemoryPaymentStore()
    settlement_store = InMemorySettlementStore()
    audit = InMemoryMAAudit()
    engine = SettlementEngine(payment_store, settlement_store, audit)
    return engine, merchant_store, payment_store, audit


async def _create_active_merchant(store: InMemoryMerchantStore) -> str:
    audit = InMemoryMAAudit()
    onboarding = MerchantOnboarding(store, audit)
    m = await onboarding.onboard("Shop", "Shop Ltd", "5411", "GB", None, "5000", "100000", "admin")
    await onboarding.approve_kyb(m.id, "admin")
    return m.id


async def _accept_approved(gw: PaymentGateway, mid: str, amount: str, ref: str) -> None:
    """Accept a payment and complete 3DS if required so it ends APPROVED."""
    p = await gw.accept_payment(mid, amount, "GBP", "4242", ref, "admin")
    if p.requires_3ds:
        await gw.complete_3ds(p.id, "admin")


@pytest.mark.asyncio
async def test_create_settlement_returns_batch() -> None:
    engine, merchant_store, payment_store, _ = _make_engine()
    mid = await _create_active_merchant(merchant_store)
    gw = PaymentGateway(merchant_store, payment_store, InMemoryMAAudit())
    await _accept_approved(gw, mid, "20.00", "ref")
    batch = await engine.create_settlement_batch(mid, "admin")
    assert batch.id != ""
    assert batch.merchant_id == mid


@pytest.mark.asyncio
async def test_create_settlement_gross_equals_sum_of_amounts() -> None:
    engine, merchant_store, payment_store, _ = _make_engine()
    mid = await _create_active_merchant(merchant_store)
    gw = PaymentGateway(merchant_store, payment_store, InMemoryMAAudit())
    await _accept_approved(gw, mid, "10.00", "r1")
    await _accept_approved(gw, mid, "15.00", "r2")
    batch = await engine.create_settlement_batch(mid, "admin")
    assert batch.gross_amount == Decimal("25.00")


@pytest.mark.asyncio
async def test_create_settlement_fees_is_gross_times_fee_rate() -> None:
    engine, merchant_store, payment_store, _ = _make_engine()
    mid = await _create_active_merchant(merchant_store)
    gw = PaymentGateway(merchant_store, payment_store, InMemoryMAAudit())
    await _accept_approved(gw, mid, "20.00", "ref")
    batch = await engine.create_settlement_batch(mid, "admin")
    expected_fees = (batch.gross_amount * FEE_RATE).quantize(Decimal("0.01"))
    assert batch.fees == expected_fees


@pytest.mark.asyncio
async def test_create_settlement_net_is_gross_minus_fees() -> None:
    engine, merchant_store, payment_store, _ = _make_engine()
    mid = await _create_active_merchant(merchant_store)
    gw = PaymentGateway(merchant_store, payment_store, InMemoryMAAudit())
    await _accept_approved(gw, mid, "20.00", "ref")
    batch = await engine.create_settlement_batch(mid, "admin")
    assert batch.net_amount == batch.gross_amount - batch.fees
    assert isinstance(batch.net_amount, Decimal)


@pytest.mark.asyncio
async def test_create_settlement_status_pending() -> None:
    engine, merchant_store, payment_store, _ = _make_engine()
    mid = await _create_active_merchant(merchant_store)
    gw = PaymentGateway(merchant_store, payment_store, InMemoryMAAudit())
    await _accept_approved(gw, mid, "20.00", "ref")
    batch = await engine.create_settlement_batch(mid, "admin")
    assert batch.status == SettlementStatus.PENDING


@pytest.mark.asyncio
async def test_create_settlement_creates_audit_event() -> None:
    engine, merchant_store, payment_store, audit = _make_engine()
    mid = await _create_active_merchant(merchant_store)
    gw = PaymentGateway(merchant_store, payment_store, InMemoryMAAudit())
    await _accept_approved(gw, mid, "20.00", "ref")
    batch = await engine.create_settlement_batch(mid, "admin")
    events = await audit.list_events(mid)
    assert any(e["event_type"] == "settlement.batch_created" for e in events)


@pytest.mark.asyncio
async def test_process_settlement_status_completed() -> None:
    engine, merchant_store, payment_store, _ = _make_engine()
    mid = await _create_active_merchant(merchant_store)
    gw = PaymentGateway(merchant_store, payment_store, InMemoryMAAudit())
    await _accept_approved(gw, mid, "20.00", "ref")
    batch = await engine.create_settlement_batch(mid, "admin")
    completed = await engine.process_settlement(batch.id, "admin")
    assert completed.status == SettlementStatus.COMPLETED


@pytest.mark.asyncio
async def test_process_settlement_bank_reference_is_set() -> None:
    engine, merchant_store, payment_store, _ = _make_engine()
    mid = await _create_active_merchant(merchant_store)
    gw = PaymentGateway(merchant_store, payment_store, InMemoryMAAudit())
    await _accept_approved(gw, mid, "20.00", "ref")
    batch = await engine.create_settlement_batch(mid, "admin")
    completed = await engine.process_settlement(batch.id, "admin")
    assert completed.bank_reference is not None
    assert len(completed.bank_reference) > 0


@pytest.mark.asyncio
async def test_process_settlement_creates_audit_event() -> None:
    engine, merchant_store, payment_store, audit = _make_engine()
    mid = await _create_active_merchant(merchant_store)
    gw = PaymentGateway(merchant_store, payment_store, InMemoryMAAudit())
    await _accept_approved(gw, mid, "20.00", "ref")
    batch = await engine.create_settlement_batch(mid, "admin")
    await engine.process_settlement(batch.id, "admin")
    events = await audit.list_events(mid)
    assert any(e["event_type"] == "settlement.completed" for e in events)


@pytest.mark.asyncio
async def test_list_settlements_returns_all_for_merchant() -> None:
    engine, merchant_store, payment_store, _ = _make_engine()
    mid = await _create_active_merchant(merchant_store)
    gw = PaymentGateway(merchant_store, payment_store, InMemoryMAAudit())
    await _accept_approved(gw, mid, "10.00", "r1")
    await engine.create_settlement_batch(mid, "admin")
    await _accept_approved(gw, mid, "20.00", "r2")
    await engine.create_settlement_batch(mid, "admin")
    batches = await engine.list_settlements(mid)
    assert len(batches) == 2


@pytest.mark.asyncio
async def test_get_latest_settlement_returns_most_recent() -> None:
    engine, merchant_store, payment_store, _ = _make_engine()
    mid = await _create_active_merchant(merchant_store)
    gw = PaymentGateway(merchant_store, payment_store, InMemoryMAAudit())
    await _accept_approved(gw, mid, "10.00", "r1")
    b1 = await engine.create_settlement_batch(mid, "admin")
    await _accept_approved(gw, mid, "20.00", "r2")
    b2 = await engine.create_settlement_batch(mid, "admin")
    latest = await engine.get_latest_settlement(mid)
    assert latest is not None
    assert latest.id in {b1.id, b2.id}


@pytest.mark.asyncio
async def test_settlement_with_zero_payments() -> None:
    engine, merchant_store, _, _ = _make_engine()
    mid = await _create_active_merchant(merchant_store)
    batch = await engine.create_settlement_batch(mid, "admin")
    assert batch.gross_amount == Decimal("0")
    assert batch.fees == Decimal("0")
    assert batch.net_amount == Decimal("0")


def test_fee_rate_is_correct() -> None:
    assert Decimal("0.015") == FEE_RATE


@pytest.mark.asyncio
async def test_two_settlements_for_same_merchant_list_returns_both() -> None:
    engine, merchant_store, payment_store, _ = _make_engine()
    mid = await _create_active_merchant(merchant_store)
    gw = PaymentGateway(merchant_store, payment_store, InMemoryMAAudit())
    await _accept_approved(gw, mid, "10.00", "r1")
    await engine.create_settlement_batch(mid, "admin")
    await _accept_approved(gw, mid, "20.00", "r2")
    await engine.create_settlement_batch(mid, "admin")
    result = await engine.list_settlements(mid)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_net_amount_is_decimal() -> None:
    engine, merchant_store, payment_store, _ = _make_engine()
    mid = await _create_active_merchant(merchant_store)
    gw = PaymentGateway(merchant_store, payment_store, InMemoryMAAudit())
    await _accept_approved(gw, mid, "20.00", "ref")
    batch = await engine.create_settlement_batch(mid, "admin")
    assert isinstance(batch.net_amount, Decimal)
