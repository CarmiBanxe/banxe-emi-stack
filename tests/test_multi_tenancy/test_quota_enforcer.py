"""Tests for services/multi_tenancy/quota_enforcer.py"""

from decimal import Decimal

import pytest

from services.multi_tenancy.models import (
    InMemoryQuotaPort,
    InMemoryTenantPort,
    Tenant,
    TenantStatus,
    TenantTier,
)
from services.multi_tenancy.quota_enforcer import QUOTA_LIMITS, QuotaEnforcer


def _make_tenant(tenant_id: str, tier: TenantTier) -> Tenant:
    from services.multi_tenancy.tenant_manager import (
        TIER_DAILY_TX,
        TIER_ISOLATION,
        TIER_MONTHLY_FEE,
    )

    return Tenant(
        tenant_id=tenant_id,
        name="TestCo",
        tier=tier,
        status=TenantStatus.ACTIVE,
        isolation_level=TIER_ISOLATION[tier],
        monthly_fee=TIER_MONTHLY_FEE[tier],
        daily_tx_limit=TIER_DAILY_TX[tier],
        jurisdiction="GB",
    )


def _make_enforcer(
    tier: TenantTier = TenantTier.BASIC, tenant_id: str = "ten_abc"
) -> tuple[QuotaEnforcer, str]:
    tp = InMemoryTenantPort()
    tp.save(_make_tenant(tenant_id, tier))
    qp = InMemoryQuotaPort()
    enf = QuotaEnforcer(quota_port=qp, tenant_port=tp)
    return enf, tenant_id


def test_check_tx_quota_ok():
    enf, tid = _make_enforcer(TenantTier.BASIC)
    ok, msg = enf.check_tx_quota(tid, Decimal("100.00"))
    assert ok is True
    assert msg == "ok"


def test_check_tx_quota_daily_limit_exceeded():
    enf, tid = _make_enforcer(TenantTier.BASIC)
    # Fill up daily quota
    for _ in range(1000):
        enf.record_transaction(tid, Decimal("1.00"))
    ok, msg = enf.check_tx_quota(tid, Decimal("1.00"))
    assert ok is False
    assert "1000" in msg


def test_check_monthly_volume_ok():
    enf, tid = _make_enforcer(TenantTier.BASIC)
    assert enf.check_monthly_volume(tid, Decimal("100.00")) is True


def test_check_monthly_volume_limit():
    enf, tid = _make_enforcer(TenantTier.BASIC)
    enf.record_transaction(tid, Decimal("49999.99"))
    # One more should push over 50000
    ok, msg = enf.check_tx_quota(tid, Decimal("0.02"))
    assert ok is False


def test_record_transaction_increments_used():
    enf, tid = _make_enforcer(TenantTier.BUSINESS)
    enf.record_transaction(tid, Decimal("500.00"))
    quota = enf.get_quota_status(tid)
    assert quota.daily_tx_used == 1
    assert quota.monthly_volume_gbp == Decimal("500.00")


def test_reset_daily_quota():
    enf, tid = _make_enforcer(TenantTier.BASIC)
    enf.record_transaction(tid, Decimal("10.00"))
    enf.reset_daily_quota(tid)
    quota = enf.get_quota_status(tid)
    assert quota.daily_tx_used == 0
    # Monthly volume should persist
    assert quota.monthly_volume_gbp == Decimal("10.00")


def test_get_quota_report_fields():
    enf, tid = _make_enforcer(TenantTier.BUSINESS)
    enf.record_transaction(tid, Decimal("1000.00"))
    report = enf.get_quota_report(tid)
    assert "daily_tx_used" in report
    assert "daily_tx_limit" in report
    assert "monthly_volume_gbp" in report
    assert "monthly_volume_limit_gbp" in report
    assert "daily_tx_pct" in report


def test_quota_limits_constants_are_decimal():
    for tier, limits in QUOTA_LIMITS.items():
        assert isinstance(limits["monthly_vol_gbp"], Decimal)


def test_quota_limits_basic():
    assert QUOTA_LIMITS[TenantTier.BASIC]["daily_tx"] == 1000
    assert QUOTA_LIMITS[TenantTier.BASIC]["monthly_vol_gbp"] == Decimal("50000")


def test_quota_limits_business():
    assert QUOTA_LIMITS[TenantTier.BUSINESS]["daily_tx"] == 10000
    assert QUOTA_LIMITS[TenantTier.BUSINESS]["monthly_vol_gbp"] == Decimal("500000")


def test_quota_limits_enterprise():
    assert QUOTA_LIMITS[TenantTier.ENTERPRISE]["daily_tx"] == 999999


def test_quota_missing_tenant_raises():
    enf = QuotaEnforcer()
    with pytest.raises(ValueError, match="not found"):
        enf.get_quota_status("ten_missing")


def test_check_tx_quota_missing_tenant_raises():
    enf = QuotaEnforcer()
    with pytest.raises(ValueError, match="not found"):
        enf.check_tx_quota("ten_missing", Decimal("1.00"))


def test_enterprise_quota_very_high():
    enf, tid = _make_enforcer(TenantTier.ENTERPRISE)
    for _ in range(100):
        enf.record_transaction(tid, Decimal("1000.00"))
    ok, msg = enf.check_tx_quota(tid, Decimal("999.00"))
    assert ok is True


def test_quota_amounts_are_decimal():
    enf, tid = _make_enforcer(TenantTier.BASIC)
    enf.record_transaction(tid, Decimal("42.50"))
    quota = enf.get_quota_status(tid)
    assert isinstance(quota.monthly_volume_gbp, Decimal)
