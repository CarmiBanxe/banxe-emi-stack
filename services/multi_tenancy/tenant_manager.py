"""
services/multi_tenancy/tenant_manager.py — Tenant lifecycle management
IL-MT-01 | Phase 43 | banxe-emi-stack
I-02: jurisdiction block. I-12: SHA-256 IDs. I-14: immutable audit.
I-24: append-only. I-27: HITL for irreversible actions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import hashlib

from services.multi_tenancy.models import (
    HITLProposal,
    InMemoryQuotaPort,
    InMemoryTenantAuditPort,
    InMemoryTenantPort,
    IsolationLevel,
    QuotaPort,
    Tenant,
    TenantAuditEntry,
    TenantAuditPort,
    TenantPort,
    TenantStatus,
    TenantTier,
)

BLOCKED_JURISDICTIONS: frozenset[str] = frozenset(
    {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}
)

TIER_MONTHLY_FEE: dict[TenantTier, Decimal] = {
    TenantTier.BASIC: Decimal("10.00"),
    TenantTier.BUSINESS: Decimal("99.00"),
    TenantTier.ENTERPRISE: Decimal("999.00"),
}

TIER_DAILY_TX: dict[TenantTier, int] = {
    TenantTier.BASIC: 1000,
    TenantTier.BUSINESS: 10000,
    TenantTier.ENTERPRISE: 999999,
}

TIER_ISOLATION: dict[TenantTier, IsolationLevel] = {
    TenantTier.BASIC: IsolationLevel.SHARED,
    TenantTier.BUSINESS: IsolationLevel.SCHEMA,
    TenantTier.ENTERPRISE: IsolationLevel.DEDICATED,
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _make_tenant_id(name: str, timestamp: str) -> str:
    """I-12: SHA-256 deterministic tenant ID."""
    digest = hashlib.sha256(f"{name}{timestamp}".encode()).hexdigest()
    return f"ten_{digest[:8]}"


class TenantManager:
    """Manages tenant lifecycle: provision, activate, suspend, terminate."""

    def __init__(
        self,
        tenant_port: TenantPort | None = None,
        audit_port: TenantAuditPort | None = None,
        quota_port: QuotaPort | None = None,
    ) -> None:
        self._tenants: TenantPort = tenant_port or InMemoryTenantPort()
        self._audit: TenantAuditPort = audit_port or InMemoryTenantAuditPort()
        self._quotas: QuotaPort = quota_port or InMemoryQuotaPort()

    def _audit_write(self, tenant_id: str, action: str, actor: str, details: dict) -> None:  # noqa: ANN001
        """Write immutable audit entry (I-14, I-24)."""
        import uuid

        entry = TenantAuditEntry(
            entry_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            action=action,
            actor=actor,
            timestamp=_now_iso(),
            details=details,
        )
        self._audit.append(entry)

    def provision_tenant(
        self, name: str, tier: str, jurisdiction: str, kyb_docs: list[str]
    ) -> HITLProposal:
        """I-27: provisioning is irreversible — returns HITL proposal."""
        if jurisdiction in BLOCKED_JURISDICTIONS:  # I-02
            raise ValueError(f"Jurisdiction {jurisdiction!r} is blocked (I-02)")
        ts = _now_iso()
        tenant_id = _make_tenant_id(name, ts)
        self._audit_write(
            tenant_id,
            "PROVISION_REQUESTED",
            "system",
            {
                "name": name,
                "tier": tier,
                "jurisdiction": jurisdiction,
                "kyb_docs_count": len(kyb_docs),
            },
        )
        return HITLProposal(
            action="provision_tenant",
            tenant_id=tenant_id,
            requires_approval_from="MLRO",
            reason=f"Provision tenant '{name}' in {jurisdiction} at tier {tier}",
        )

    def activate_tenant(self, tenant_id: str, actor: str) -> Tenant:
        """Activate tenant after KYB verification. Creates CASS 7 pool."""
        tenant = self._tenants.get(tenant_id)
        if tenant is None:
            raise ValueError(f"Tenant {tenant_id!r} not found")
        if not tenant.kyb_verified:
            raise ValueError(f"Tenant {tenant_id!r} KYB not verified")
        cass_pool_id = f"pool_{tenant_id}"
        activated = Tenant(
            tenant_id=tenant.tenant_id,
            name=tenant.name,
            tier=tenant.tier,
            status=TenantStatus.ACTIVE,
            isolation_level=tenant.isolation_level,
            monthly_fee=tenant.monthly_fee,
            daily_tx_limit=tenant.daily_tx_limit,
            jurisdiction=tenant.jurisdiction,
            kyb_verified=tenant.kyb_verified,
            cass_pool_id=cass_pool_id,  # CASS 7
        )
        self._tenants.save(activated)
        self._audit_write(tenant_id, "ACTIVATED", actor, {"cass_pool_id": cass_pool_id})
        return activated

    def suspend_tenant(self, tenant_id: str, reason: str, actor: str) -> HITLProposal:
        """I-27: suspension is reversible but needs HITL."""
        if self._tenants.get(tenant_id) is None:
            raise ValueError(f"Tenant {tenant_id!r} not found")
        self._audit_write(tenant_id, "SUSPEND_REQUESTED", actor, {"reason": reason})
        return HITLProposal(
            action="suspend_tenant",
            tenant_id=tenant_id,
            requires_approval_from="COMPLIANCE",
            reason=reason,
        )

    def terminate_tenant(self, tenant_id: str, reason: str, actor: str) -> HITLProposal:
        """I-27: termination irreversible — data deletion requires HITL."""
        if self._tenants.get(tenant_id) is None:
            raise ValueError(f"Tenant {tenant_id!r} not found")
        self._audit_write(tenant_id, "TERMINATE_REQUESTED", actor, {"reason": reason})
        return HITLProposal(
            action="terminate_tenant",
            tenant_id=tenant_id,
            requires_approval_from="CEO",
            reason=reason,
        )

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        return self._tenants.get(tenant_id)

    def list_tenants(self, status: str | None = None) -> list[Tenant]:
        """List tenants, optionally filtered by status."""
        if status is None:
            return self._tenants.list_active()
        active = self._tenants.list_active()
        try:
            s = TenantStatus(status)
        except ValueError:
            return []
        if s == TenantStatus.ACTIVE:
            return active
        return []

    def update_tier(self, tenant_id: str, new_tier: str, actor: str) -> HITLProposal:
        """I-27: billing change requires HITL."""
        tenant = self._tenants.get(tenant_id)
        if tenant is None:
            raise ValueError(f"Tenant {tenant_id!r} not found")
        tier = TenantTier(new_tier)
        self._audit_write(
            tenant_id,
            "TIER_CHANGE_REQUESTED",
            actor,
            {
                "old_tier": tenant.tier.value,
                "new_tier": tier.value,
            },
        )
        return HITLProposal(
            action="update_tier",
            tenant_id=tenant_id,
            requires_approval_from="BILLING",
            reason=f"Change tier from {tenant.tier} to {new_tier}",
        )

    def verify_kyb(self, tenant_id: str, verification_ref: str, actor: str) -> Tenant:
        """Mark tenant KYB as verified."""
        tenant = self._tenants.get(tenant_id)
        if tenant is None:
            raise ValueError(f"Tenant {tenant_id!r} not found")
        tier = tenant.tier
        verified = Tenant(
            tenant_id=tenant.tenant_id,
            name=tenant.name,
            tier=tier,
            status=tenant.status,
            isolation_level=tenant.isolation_level,
            monthly_fee=tenant.monthly_fee,
            daily_tx_limit=tenant.daily_tx_limit,
            jurisdiction=tenant.jurisdiction,
            kyb_verified=True,
            cass_pool_id=tenant.cass_pool_id,
        )
        self._tenants.save(verified)
        self._audit_write(tenant_id, "KYB_VERIFIED", actor, {"ref": verification_ref})
        return verified

    def _create_tenant_record(
        self, tenant_id: str, name: str, tier: TenantTier, jurisdiction: str
    ) -> Tenant:
        """Create and persist a tenant record (used after HITL approval)."""
        tenant = Tenant(
            tenant_id=tenant_id,
            name=name,
            tier=tier,
            status=TenantStatus.PENDING_KYB,
            isolation_level=TIER_ISOLATION[tier],
            monthly_fee=TIER_MONTHLY_FEE[tier],
            daily_tx_limit=TIER_DAILY_TX[tier],
            jurisdiction=jurisdiction,
            kyb_verified=False,
        )
        self._tenants.save(tenant)
        return tenant
