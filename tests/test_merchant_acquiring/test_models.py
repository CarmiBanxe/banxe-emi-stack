"""
tests/test_merchant_acquiring/test_models.py
IL-MAG-01 | Phase 20 — Domain model and InMemory stub tests.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from services.merchant_acquiring.models import (
    ChargebackReason,
    DisputeCase,
    DisputeStatus,
    InMemoryDisputeStore,
    InMemoryMAAudit,
    InMemoryMerchantStore,
    InMemoryPaymentStore,
    InMemorySettlementStore,
    Merchant,
    MerchantRiskScore,
    MerchantRiskTier,
    MerchantStatus,
    PaymentAcceptance,
    PaymentResult,
    SettlementBatch,
    SettlementStatus,
)

_NOW = datetime.now(UTC)


def _make_merchant(mid: str = "m-001") -> Merchant:
    return Merchant(
        id=mid,
        name="Test Shop",
        legal_name="Test Shop Ltd",
        mcc="5411",
        country="GB",
        website="https://test.shop",
        status=MerchantStatus.ACTIVE,
        risk_tier=MerchantRiskTier.LOW,
        onboarded_at=_NOW,
        daily_limit=Decimal("10000"),
        monthly_limit=Decimal("200000"),
    )


def _make_payment(pid: str = "p-001", mid: str = "m-001") -> PaymentAcceptance:
    return PaymentAcceptance(
        id=pid,
        merchant_id=mid,
        amount=Decimal("25.00"),
        currency="GBP",
        result=PaymentResult.APPROVED,
        card_last_four="4242",
        reference="ref-001",
        requires_3ds=False,
        created_at=_NOW,
        completed_at=_NOW,
        acquirer_ref="ACQ-123456",
    )


def _make_settlement(sid: str = "s-001", mid: str = "m-001") -> SettlementBatch:
    return SettlementBatch(
        id=sid,
        merchant_id=mid,
        settlement_date=_NOW,
        gross_amount=Decimal("100.00"),
        fees=Decimal("1.50"),
        net_amount=Decimal("98.50"),
        payment_count=4,
        status=SettlementStatus.PENDING,
        bank_reference=None,
    )


def _make_dispute(did: str = "d-001", mid: str = "m-001") -> DisputeCase:
    return DisputeCase(
        id=did,
        merchant_id=mid,
        payment_id="p-001",
        amount=Decimal("25.00"),
        currency="GBP",
        reason=ChargebackReason.FRAUD,
        status=DisputeStatus.RECEIVED,
        received_at=_NOW,
        resolved_at=None,
        evidence_submitted=False,
    )


def test_merchant_frozen_dataclass() -> None:
    m = _make_merchant()
    with pytest.raises((AttributeError, TypeError)):
        m.name = "new"  # type: ignore[misc]


def test_merchant_decimal_daily_limit() -> None:
    m = _make_merchant()
    assert isinstance(m.daily_limit, Decimal)
    assert m.daily_limit == Decimal("10000")


def test_merchant_status_enum_values() -> None:
    assert MerchantStatus.PENDING_KYB.value == "PENDING_KYB"
    assert MerchantStatus.ACTIVE.value == "ACTIVE"
    assert MerchantStatus.SUSPENDED.value == "SUSPENDED"
    assert MerchantStatus.TERMINATED.value == "TERMINATED"


def test_payment_requires_3ds_flag() -> None:
    p = PaymentAcceptance(
        id="p-001",
        merchant_id="m-001",
        amount=Decimal("50.00"),
        currency="GBP",
        result=PaymentResult.PENDING_3DS,
        card_last_four="1234",
        reference="ref",
        requires_3ds=True,
        created_at=_NOW,
        completed_at=None,
        acquirer_ref=None,
    )
    assert p.requires_3ds is True
    assert p.result == PaymentResult.PENDING_3DS


def test_settlement_batch_net_amount() -> None:
    s = _make_settlement()
    assert s.net_amount == s.gross_amount - s.fees
    assert isinstance(s.net_amount, Decimal)


def test_settlement_status_enum_values() -> None:
    assert SettlementStatus.PENDING.value == "PENDING"
    assert SettlementStatus.COMPLETED.value == "COMPLETED"
    assert SettlementStatus.FAILED.value == "FAILED"


def test_dispute_resolved_at_none_initially() -> None:
    d = _make_dispute()
    assert d.resolved_at is None
    assert d.evidence_submitted is False


def test_chargeback_reason_enum_values() -> None:
    assert ChargebackReason.FRAUD.value == "FRAUD"
    assert ChargebackReason.ITEM_NOT_RECEIVED.value == "ITEM_NOT_RECEIVED"
    assert ChargebackReason.DUPLICATE.value == "DUPLICATE"
    assert ChargebackReason.SUBSCRIPTION_CANCELLED.value == "SUBSCRIPTION_CANCELLED"


def test_risk_score_chargeback_ratio_is_float() -> None:
    score = MerchantRiskScore(
        merchant_id="m-001",
        computed_at=_NOW,
        chargeback_ratio=0.05,
        volume_anomaly=0.0,
        mcc_risk=10.0,
        overall_score=5.0,
        risk_tier=MerchantRiskTier.LOW,
    )
    assert isinstance(score.chargeback_ratio, float)
    assert not isinstance(score.chargeback_ratio, Decimal)


@pytest.mark.asyncio
async def test_merchant_store_save_get() -> None:
    store = InMemoryMerchantStore()
    m = _make_merchant()
    await store.save(m)
    result = await store.get("m-001")
    assert result == m


@pytest.mark.asyncio
async def test_merchant_store_get_missing_returns_none() -> None:
    store = InMemoryMerchantStore()
    assert await store.get("nonexistent") is None


@pytest.mark.asyncio
async def test_merchant_store_list_all() -> None:
    store = InMemoryMerchantStore()
    m1 = _make_merchant("m-001")
    m2 = _make_merchant("m-002")
    await store.save(m1)
    await store.save(m2)
    result = await store.list_all()
    assert len(result) == 2


@pytest.mark.asyncio
async def test_payment_store_save_get() -> None:
    store = InMemoryPaymentStore()
    p = _make_payment()
    await store.save(p)
    assert await store.get("p-001") == p


@pytest.mark.asyncio
async def test_payment_store_list_by_merchant() -> None:
    store = InMemoryPaymentStore()
    await store.save(_make_payment("p-001", "m-001"))
    await store.save(_make_payment("p-002", "m-001"))
    await store.save(_make_payment("p-003", "m-002"))
    result = await store.list_by_merchant("m-001")
    assert len(result) == 2


@pytest.mark.asyncio
async def test_settlement_store_save_get() -> None:
    store = InMemorySettlementStore()
    s = _make_settlement()
    await store.save(s)
    assert await store.get("s-001") == s


@pytest.mark.asyncio
async def test_settlement_store_list_by_merchant() -> None:
    store = InMemorySettlementStore()
    await store.save(_make_settlement("s-001", "m-001"))
    await store.save(_make_settlement("s-002", "m-002"))
    result = await store.list_by_merchant("m-001")
    assert len(result) == 1


@pytest.mark.asyncio
async def test_settlement_store_get_latest() -> None:
    store = InMemorySettlementStore()
    earlier = SettlementBatch(
        id="s-001",
        merchant_id="m-001",
        settlement_date=_NOW - timedelta(days=1),
        gross_amount=Decimal("50"),
        fees=Decimal("0.75"),
        net_amount=Decimal("49.25"),
        payment_count=2,
        status=SettlementStatus.COMPLETED,
        bank_reference=None,
    )
    later = SettlementBatch(
        id="s-002",
        merchant_id="m-001",
        settlement_date=_NOW,
        gross_amount=Decimal("100"),
        fees=Decimal("1.50"),
        net_amount=Decimal("98.50"),
        payment_count=4,
        status=SettlementStatus.PENDING,
        bank_reference=None,
    )
    await store.save(earlier)
    await store.save(later)
    result = await store.get_latest("m-001")
    assert result is not None
    assert result.id == "s-002"


@pytest.mark.asyncio
async def test_dispute_store_save_get() -> None:
    store = InMemoryDisputeStore()
    d = _make_dispute()
    await store.save(d)
    assert await store.get("d-001") == d


@pytest.mark.asyncio
async def test_dispute_store_list_by_merchant() -> None:
    store = InMemoryDisputeStore()
    await store.save(_make_dispute("d-001", "m-001"))
    await store.save(_make_dispute("d-002", "m-002"))
    result = await store.list_by_merchant("m-001")
    assert len(result) == 1


@pytest.mark.asyncio
async def test_ma_audit_log_and_list() -> None:
    audit = InMemoryMAAudit()
    await audit.log("test.event", "m-001", "actor", {"key": "value"})
    events = await audit.list_events()
    assert len(events) == 1
    assert events[0]["event_type"] == "test.event"


@pytest.mark.asyncio
async def test_ma_audit_filter_by_merchant() -> None:
    audit = InMemoryMAAudit()
    await audit.log("event.a", "m-001", "actor", {})
    await audit.log("event.b", "m-002", "actor", {})
    events = await audit.list_events("m-001")
    assert len(events) == 1
    assert events[0]["merchant_id"] == "m-001"
