"""
services/multi_tenancy/quota_enforcer.py — Per-tier quota enforcement
IL-MT-01 | Phase 43 | banxe-emi-stack
I-01: Decimal for all GBP amounts and limits.
"""

from __future__ import annotations

from decimal import Decimal

from services.multi_tenancy.models import (
    InMemoryQuotaPort,
    InMemoryTenantPort,
    QuotaPort,
    TenantPort,
    TenantQuota,
    TenantTier,
)

QUOTA_LIMITS: dict[TenantTier, dict] = {
    TenantTier.BASIC: {"daily_tx": 1000, "monthly_vol_gbp": Decimal("50000")},
    TenantTier.BUSINESS: {"daily_tx": 10000, "monthly_vol_gbp": Decimal("500000")},
    TenantTier.ENTERPRISE: {"daily_tx": 999999, "monthly_vol_gbp": Decimal("99999999")},
}


class QuotaEnforcer:
    """Enforces per-tenant daily transaction and monthly volume quotas."""

    def __init__(
        self,
        quota_port: QuotaPort | None = None,
        tenant_port: TenantPort | None = None,
    ) -> None:
        self._quotas: QuotaPort = quota_port or InMemoryQuotaPort()
        self._tenants: TenantPort = tenant_port or InMemoryTenantPort()

    def _get_or_init_quota(self, tenant_id: str) -> TenantQuota:
        """Get quota or initialise from tenant tier defaults."""
        quota = self._quotas.get(tenant_id)
        if quota is not None:
            return quota
        tenant = self._tenants.get(tenant_id)
        if tenant is None:
            raise ValueError(f"Tenant {tenant_id!r} not found")
        limits = QUOTA_LIMITS[tenant.tier]
        quota = TenantQuota(
            tenant_id=tenant_id,
            daily_tx_used=0,
            daily_tx_limit=limits["daily_tx"],
            monthly_volume_gbp=Decimal("0"),
            monthly_volume_limit_gbp=limits["monthly_vol_gbp"],
        )
        self._quotas.save(quota)
        return quota

    def check_tx_quota(self, tenant_id: str, amount_gbp: Decimal) -> tuple[bool, str]:
        """Check if a transaction is within daily quota. I-01: Decimal amount."""
        quota = self._get_or_init_quota(tenant_id)
        if quota.daily_tx_used >= quota.daily_tx_limit:
            return False, f"Daily transaction limit {quota.daily_tx_limit} reached"
        if not self.check_monthly_volume(tenant_id, amount_gbp):
            return False, f"Monthly volume limit {quota.monthly_volume_limit_gbp} would be exceeded"
        return True, "ok"

    def record_transaction(self, tenant_id: str, amount_gbp: Decimal) -> None:
        """Record a completed transaction against quota. I-01: Decimal."""
        quota = self._get_or_init_quota(tenant_id)
        updated = TenantQuota(
            tenant_id=tenant_id,
            daily_tx_used=quota.daily_tx_used + 1,
            daily_tx_limit=quota.daily_tx_limit,
            monthly_volume_gbp=quota.monthly_volume_gbp + amount_gbp,
            monthly_volume_limit_gbp=quota.monthly_volume_limit_gbp,
        )
        self._quotas.save(updated)

    def get_quota_status(self, tenant_id: str) -> TenantQuota:
        """Get current quota status for tenant."""
        return self._get_or_init_quota(tenant_id)

    def reset_daily_quota(self, tenant_id: str) -> None:
        """Reset daily transaction counter (called by scheduler at midnight)."""
        quota = self._get_or_init_quota(tenant_id)
        reset = TenantQuota(
            tenant_id=tenant_id,
            daily_tx_used=0,
            daily_tx_limit=quota.daily_tx_limit,
            monthly_volume_gbp=quota.monthly_volume_gbp,
            monthly_volume_limit_gbp=quota.monthly_volume_limit_gbp,
        )
        self._quotas.save(reset)

    def check_monthly_volume(self, tenant_id: str, amount: Decimal) -> bool:
        """Check if additional amount fits within monthly volume limit. I-01: Decimal."""
        quota = self._get_or_init_quota(tenant_id)
        return quota.monthly_volume_gbp + amount <= quota.monthly_volume_limit_gbp

    def get_quota_report(self, tenant_id: str) -> dict:
        """Generate quota usage report for tenant."""
        quota = self._get_or_init_quota(tenant_id)
        daily_pct = (
            (quota.daily_tx_used / quota.daily_tx_limit * 100) if quota.daily_tx_limit else 0
        )
        monthly_pct_raw = quota.monthly_volume_gbp / quota.monthly_volume_limit_gbp * 100
        monthly_pct = float(monthly_pct_raw) if quota.monthly_volume_limit_gbp else 0
        return {
            "tenant_id": tenant_id,
            "daily_tx_used": quota.daily_tx_used,
            "daily_tx_limit": quota.daily_tx_limit,
            "daily_tx_pct": round(daily_pct, 2),
            "monthly_volume_gbp": str(quota.monthly_volume_gbp),
            "monthly_volume_limit_gbp": str(quota.monthly_volume_limit_gbp),
            "monthly_volume_pct": round(monthly_pct, 2),
        }
