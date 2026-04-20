"""
services/multi_tenancy/billing_engine.py — Tenant billing & invoice generation
IL-MT-01 | Phase 43 | banxe-emi-stack
I-01: Decimal for all monetary values (GBP).
I-27: payment failure → HITLProposal.
"""

from __future__ import annotations

from decimal import Decimal

from services.multi_tenancy.models import (
    HITLProposal,
    InMemoryTenantPort,
    TenantPort,
    TenantTier,
)

TIER_MONTHLY_FEE: dict[TenantTier, Decimal] = {
    TenantTier.BASIC: Decimal("10.00"),
    TenantTier.BUSINESS: Decimal("99.00"),
    TenantTier.ENTERPRISE: Decimal("999.00"),
}

OVERAGE_FEE_PER_TX = Decimal("0.01")  # I-01: per excess transaction

TIER_DAILY_TX_LIMIT: dict[TenantTier, int] = {
    TenantTier.BASIC: 1000,
    TenantTier.BUSINESS: 10000,
    TenantTier.ENTERPRISE: 999999,
}


class TenantBillingEngine:
    """Calculates and generates tenant invoices."""

    def __init__(self, tenant_port: TenantPort | None = None) -> None:
        self._tenants: TenantPort = tenant_port or InMemoryTenantPort()
        # In-memory billing records: tenant_id -> list of charge dicts
        self._charges: dict[str, list[dict]] = {}

    def _get_tier(self, tenant_id: str) -> TenantTier:
        tenant = self._tenants.get(tenant_id)
        if tenant is None:
            raise ValueError(f"Tenant {tenant_id!r} not found")
        return tenant.tier

    def calculate_monthly_invoice(self, tenant_id: str, period: str) -> dict:
        """Calculate full monthly invoice including base fee + overages. I-01: Decimal."""
        tier = self._get_tier(tenant_id)
        base_fee: Decimal = TIER_MONTHLY_FEE[tier]
        overage: Decimal = self._calculate_overage(tenant_id)
        total: Decimal = base_fee + overage
        return {
            "tenant_id": tenant_id,
            "period": period,
            "tier": tier.value,
            "base_fee": str(base_fee),
            "overage": str(overage),
            "amount": str(total),  # I-01: string representation
            "currency": "GBP",
        }

    def _calculate_overage(self, tenant_id: str) -> Decimal:
        """Calculate overage from recorded charges."""
        charges = self._charges.get(tenant_id, [])
        total_over = sum(c.get("excess_tx", 0) for c in charges)
        return Decimal(str(total_over)) * OVERAGE_FEE_PER_TX  # I-01

    def apply_usage_charges(self, tenant_id: str, tx_count: int, volume_gbp: Decimal) -> Decimal:
        """Apply usage charges for the period. I-01: Decimal."""
        tier = self._get_tier(tenant_id)
        limit = TIER_DAILY_TX_LIMIT[tier]
        excess = max(0, tx_count - limit)
        overage: Decimal = Decimal(str(excess)) * OVERAGE_FEE_PER_TX  # I-01
        if tenant_id not in self._charges:
            self._charges[tenant_id] = []
        self._charges[tenant_id].append(
            {
                "tx_count": tx_count,
                "volume_gbp": str(volume_gbp),
                "excess_tx": excess,
                "overage": str(overage),
            }
        )
        return overage

    def get_billing_summary(self, tenant_id: str) -> dict:
        """Get billing summary for tenant."""
        tier = self._get_tier(tenant_id)
        charges = self._charges.get(tenant_id, [])
        total_tx = sum(c.get("tx_count", 0) for c in charges)
        total_overage = self._calculate_overage(tenant_id)
        return {
            "tenant_id": tenant_id,
            "tier": tier.value,
            "monthly_fee": str(TIER_MONTHLY_FEE[tier]),
            "total_transactions": total_tx,
            "total_overage": str(total_overage),
        }

    def generate_invoice(self, tenant_id: str, period: str) -> dict:
        """Generate invoice document for tenant."""
        import uuid

        invoice = self.calculate_monthly_invoice(tenant_id, period)
        invoice["invoice_id"] = f"inv_{uuid.uuid4().hex[:8]}"
        invoice["status"] = "issued"
        return invoice

    def process_payment_failure(self, tenant_id: str, reason: str) -> HITLProposal:
        """I-27: payment failure requires HITL — suspend decision."""
        return HITLProposal(
            action="process_payment_failure",
            tenant_id=tenant_id,
            requires_approval_from="BILLING",
            reason=f"Payment failure for {tenant_id}: {reason}",
        )
