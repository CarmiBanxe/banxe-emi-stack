"""
tests/test_merchant_acquiring/test_onboarding.py
IL-MAG-01 | Phase 20 — Merchant onboarding service tests.
"""

from __future__ import annotations

import pytest

from services.merchant_acquiring.merchant_onboarding import MerchantOnboarding
from services.merchant_acquiring.models import (
    InMemoryMAAudit,
    InMemoryMerchantStore,
    MerchantRiskTier,
    MerchantStatus,
)


def _make_service() -> tuple[MerchantOnboarding, InMemoryMAAudit]:
    store = InMemoryMerchantStore()
    audit = InMemoryMAAudit()
    return MerchantOnboarding(store, audit), audit


@pytest.mark.asyncio
async def test_onboard_returns_merchant_with_pending_kyb() -> None:
    svc, _ = _make_service()
    m = await svc.onboard("Shop", "Shop Ltd", "5411", "GB", None, "5000", "100000", "admin")
    assert m.status == MerchantStatus.PENDING_KYB
    assert m.id != ""


@pytest.mark.asyncio
async def test_onboard_prohibited_mcc_raises_value_error() -> None:
    svc, _ = _make_service()
    with pytest.raises(ValueError, match="prohibited"):
        await svc.onboard("Casino", "Casino Ltd", "7995", "GB", None, "5000", "100000", "admin")


@pytest.mark.asyncio
async def test_onboard_high_risk_mcc_gives_high_tier() -> None:
    svc, _ = _make_service()
    m = await svc.onboard("Pharmacy", "Pharma Ltd", "5912", "GB", None, "5000", "100000", "admin")
    assert m.risk_tier == MerchantRiskTier.HIGH


@pytest.mark.asyncio
async def test_onboard_large_daily_limit_gives_medium_tier() -> None:
    svc, _ = _make_service()
    m = await svc.onboard(
        "BigShop", "BigShop Ltd", "5411", "GB", None, "200000", "2000000", "admin"
    )
    assert m.risk_tier == MerchantRiskTier.MEDIUM


@pytest.mark.asyncio
async def test_onboard_small_limits_low_risk_mcc_gives_low_tier() -> None:
    svc, _ = _make_service()
    m = await svc.onboard("SmallShop", "Small Ltd", "5411", "GB", None, "5000", "50000", "admin")
    assert m.risk_tier == MerchantRiskTier.LOW


@pytest.mark.asyncio
async def test_onboard_creates_audit_event() -> None:
    svc, audit = _make_service()
    m = await svc.onboard("Shop", "Shop Ltd", "5411", "GB", None, "5000", "100000", "admin")
    events = await audit.list_events(m.id)
    assert any(e["event_type"] == "merchant.onboarded" for e in events)


@pytest.mark.asyncio
async def test_approve_kyb_changes_status_to_active() -> None:
    svc, _ = _make_service()
    m = await svc.onboard("Shop", "Shop Ltd", "5411", "GB", None, "5000", "100000", "admin")
    approved = await svc.approve_kyb(m.id, "admin")
    assert approved.status == MerchantStatus.ACTIVE


@pytest.mark.asyncio
async def test_approve_kyb_sets_onboarded_at() -> None:
    svc, _ = _make_service()
    m = await svc.onboard("Shop", "Shop Ltd", "5411", "GB", None, "5000", "100000", "admin")
    approved = await svc.approve_kyb(m.id, "admin")
    assert approved.onboarded_at is not None


@pytest.mark.asyncio
async def test_approve_kyb_creates_audit_event() -> None:
    svc, audit = _make_service()
    m = await svc.onboard("Shop", "Shop Ltd", "5411", "GB", None, "5000", "100000", "admin")
    await svc.approve_kyb(m.id, "admin")
    events = await audit.list_events(m.id)
    assert any(e["event_type"] == "merchant.kyb_approved" for e in events)


@pytest.mark.asyncio
async def test_approve_kyb_unknown_merchant_raises_value_error() -> None:
    svc, _ = _make_service()
    with pytest.raises(ValueError):
        await svc.approve_kyb("nonexistent-id", "admin")


@pytest.mark.asyncio
async def test_suspend_changes_status_to_suspended() -> None:
    svc, _ = _make_service()
    m = await svc.onboard("Shop", "Shop Ltd", "5411", "GB", None, "5000", "100000", "admin")
    await svc.approve_kyb(m.id, "admin")
    suspended = await svc.suspend(m.id, "Suspicious activity", "admin")
    assert suspended.status == MerchantStatus.SUSPENDED


@pytest.mark.asyncio
async def test_suspend_creates_audit_event() -> None:
    svc, audit = _make_service()
    m = await svc.onboard("Shop", "Shop Ltd", "5411", "GB", None, "5000", "100000", "admin")
    await svc.suspend(m.id, "reason", "admin")
    events = await audit.list_events(m.id)
    assert any(e["event_type"] == "merchant.suspended" for e in events)


@pytest.mark.asyncio
async def test_terminate_changes_status_to_terminated() -> None:
    svc, _ = _make_service()
    m = await svc.onboard("Shop", "Shop Ltd", "5411", "GB", None, "5000", "100000", "admin")
    terminated = await svc.terminate(m.id, "Fraud confirmed", "admin")
    assert terminated.status == MerchantStatus.TERMINATED


@pytest.mark.asyncio
async def test_terminate_creates_audit_event() -> None:
    svc, audit = _make_service()
    m = await svc.onboard("Shop", "Shop Ltd", "5411", "GB", None, "5000", "100000", "admin")
    await svc.terminate(m.id, "reason", "admin")
    events = await audit.list_events(m.id)
    assert any(e["event_type"] == "merchant.terminated" for e in events)


@pytest.mark.asyncio
async def test_get_merchant_existing() -> None:
    svc, _ = _make_service()
    m = await svc.onboard("Shop", "Shop Ltd", "5411", "GB", None, "5000", "100000", "admin")
    found = await svc.get_merchant(m.id)
    assert found is not None
    assert found.id == m.id


@pytest.mark.asyncio
async def test_get_merchant_none_for_missing() -> None:
    svc, _ = _make_service()
    result = await svc.get_merchant("does-not-exist")
    assert result is None


@pytest.mark.asyncio
async def test_list_merchants_returns_all() -> None:
    svc, _ = _make_service()
    await svc.onboard("Shop1", "Shop1 Ltd", "5411", "GB", None, "5000", "100000", "admin")
    await svc.onboard("Shop2", "Shop2 Ltd", "5411", "GB", None, "5000", "100000", "admin")
    merchants = await svc.list_merchants()
    assert len(merchants) == 2


@pytest.mark.asyncio
async def test_onboard_with_website_none() -> None:
    svc, _ = _make_service()
    m = await svc.onboard("Shop", "Shop Ltd", "5411", "GB", None, "5000", "100000", "admin")
    assert m.website is None


@pytest.mark.asyncio
async def test_two_merchants_with_same_mcc() -> None:
    svc, _ = _make_service()
    m1 = await svc.onboard("Shop1", "S1 Ltd", "5411", "GB", None, "5000", "100000", "admin")
    m2 = await svc.onboard("Shop2", "S2 Ltd", "5411", "GB", None, "5000", "100000", "admin")
    assert m1.id != m2.id
    assert m1.mcc == m2.mcc


@pytest.mark.asyncio
async def test_risk_tier_for_medium_limits() -> None:
    svc, _ = _make_service()
    # daily > 100000 with non-high-risk MCC → MEDIUM
    m = await svc.onboard("MedShop", "Med Ltd", "5411", "GB", None, "150000", "1000000", "admin")
    assert m.risk_tier == MerchantRiskTier.MEDIUM
