"""Tests for services/multi_tenancy/tenant_manager.py"""

import pytest

from services.multi_tenancy.models import (
    HITLProposal,
    InMemoryQuotaPort,
    InMemoryTenantAuditPort,
    InMemoryTenantPort,
    Tenant,
    TenantStatus,
    TenantTier,
)
from services.multi_tenancy.tenant_manager import (
    BLOCKED_JURISDICTIONS,
    TenantManager,
    _make_tenant_id,
)


def _make_mgr() -> TenantManager:
    tenant_port = InMemoryTenantPort()
    audit_port = InMemoryTenantAuditPort()
    quota_port = InMemoryQuotaPort()
    return TenantManager(tenant_port, audit_port, quota_port)


def _provision_and_create(mgr: TenantManager, name: str = "Acme", tier: str = "business") -> str:
    """Provision and manually create a tenant record for testing."""
    proposal = mgr.provision_tenant(name, tier, "GB", ["doc1.pdf"])
    tenant_id = proposal.tenant_id
    from services.multi_tenancy.tenant_manager import (
        TIER_DAILY_TX,
        TIER_ISOLATION,
        TIER_MONTHLY_FEE,
    )

    t = TenantTier(tier)
    tenant = Tenant(
        tenant_id=tenant_id,
        name=name,
        tier=t,
        status=TenantStatus.PENDING_KYB,
        isolation_level=TIER_ISOLATION[t],
        monthly_fee=TIER_MONTHLY_FEE[t],
        daily_tx_limit=TIER_DAILY_TX[t],
        jurisdiction="GB",
        kyb_verified=False,
    )
    mgr._tenants.save(tenant)
    return tenant_id


def test_provision_tenant_returns_hitl_proposal():
    mgr = _make_mgr()
    result = mgr.provision_tenant("TestCo", "basic", "GB", [])
    assert isinstance(result, HITLProposal)
    assert result.action == "provision_tenant"


def test_provision_tenant_id_starts_with_ten():
    mgr = _make_mgr()
    result = mgr.provision_tenant("TestCo", "basic", "GB", [])
    assert result.tenant_id.startswith("ten_")


def test_provision_blocked_jurisdiction_raises():
    mgr = _make_mgr()
    for jur in ["RU", "BY", "IR", "KP"]:
        with pytest.raises(ValueError, match="blocked"):
            mgr.provision_tenant("BadCo", "basic", jur, [])


def test_provision_writes_audit_entry():
    mgr = _make_mgr()
    proposal = mgr.provision_tenant("AuditCo", "basic", "GB", [])
    entries = mgr._audit.list_by_tenant(proposal.tenant_id)
    assert len(entries) >= 1
    assert entries[0].action == "PROVISION_REQUESTED"


def test_activate_tenant_requires_kyb():
    mgr = _make_mgr()
    tenant_id = _provision_and_create(mgr)
    with pytest.raises(ValueError, match="KYB"):
        mgr.activate_tenant(tenant_id, actor="admin")


def test_activate_tenant_creates_cass_pool():
    mgr = _make_mgr()
    tenant_id = _provision_and_create(mgr)
    mgr.verify_kyb(tenant_id, "REF-001", "admin")
    tenant = mgr.activate_tenant(tenant_id, actor="admin")
    assert tenant.cass_pool_id == f"pool_{tenant_id}"


def test_activate_tenant_status_becomes_active():
    mgr = _make_mgr()
    tenant_id = _provision_and_create(mgr)
    mgr.verify_kyb(tenant_id, "REF-002", "admin")
    tenant = mgr.activate_tenant(tenant_id, actor="admin")
    assert tenant.status == TenantStatus.ACTIVE


def test_activate_missing_tenant_raises():
    mgr = _make_mgr()
    with pytest.raises(ValueError, match="not found"):
        mgr.activate_tenant("ten_missing", actor="admin")


def test_suspend_tenant_returns_hitl():
    mgr = _make_mgr()
    tenant_id = _provision_and_create(mgr)
    result = mgr.suspend_tenant(tenant_id, reason="AML concern", actor="MLRO")
    assert isinstance(result, HITLProposal)
    assert result.action == "suspend_tenant"


def test_suspend_missing_tenant_raises():
    mgr = _make_mgr()
    with pytest.raises(ValueError, match="not found"):
        mgr.suspend_tenant("ten_missing", reason="test", actor="admin")


def test_terminate_tenant_returns_hitl():
    mgr = _make_mgr()
    tenant_id = _provision_and_create(mgr)
    result = mgr.terminate_tenant(tenant_id, reason="breach", actor="CEO")
    assert isinstance(result, HITLProposal)
    assert result.autonomy_level == "L4"


def test_terminate_requires_ceo_approval():
    mgr = _make_mgr()
    tenant_id = _provision_and_create(mgr)
    result = mgr.terminate_tenant(tenant_id, reason="test", actor="CEO")
    assert result.requires_approval_from == "CEO"


def test_verify_kyb_sets_flag():
    mgr = _make_mgr()
    tenant_id = _provision_and_create(mgr)
    tenant = mgr.verify_kyb(tenant_id, "REF-123", "admin")
    assert tenant.kyb_verified is True


def test_verify_kyb_writes_audit():
    mgr = _make_mgr()
    tenant_id = _provision_and_create(mgr)
    mgr.verify_kyb(tenant_id, "REF-124", "admin")
    entries = mgr._audit.list_by_tenant(tenant_id)
    actions = [e.action for e in entries]
    assert "KYB_VERIFIED" in actions


def test_update_tier_returns_hitl():
    mgr = _make_mgr()
    tenant_id = _provision_and_create(mgr)
    result = mgr.update_tier(tenant_id, "enterprise", "admin")
    assert isinstance(result, HITLProposal)
    assert result.action == "update_tier"


def test_update_tier_invalid_raises():
    mgr = _make_mgr()
    tenant_id = _provision_and_create(mgr)
    with pytest.raises(ValueError):
        mgr.update_tier(tenant_id, "premium_invalid", "admin")


def test_get_tenant_returns_none_for_missing():
    mgr = _make_mgr()
    assert mgr.get_tenant("ten_missing") is None


def test_list_tenants_returns_active():
    mgr = _make_mgr()
    tenant_id = _provision_and_create(mgr)
    mgr.verify_kyb(tenant_id, "REF-200", "admin")
    mgr.activate_tenant(tenant_id, actor="admin")
    tenants = mgr.list_tenants()
    assert any(t.tenant_id == tenant_id for t in tenants)


def test_make_tenant_id_deterministic():
    id1 = _make_tenant_id("Acme", "2026-04-20T10:00:00")
    id2 = _make_tenant_id("Acme", "2026-04-20T10:00:00")
    assert id1 == id2
    assert id1.startswith("ten_")


def test_make_tenant_id_different_inputs():
    id1 = _make_tenant_id("Acme", "2026-04-20T10:00:00")
    id2 = _make_tenant_id("Acme2", "2026-04-20T10:00:00")
    assert id1 != id2


def test_blocked_jurisdictions_complete():
    required = {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}
    assert required <= BLOCKED_JURISDICTIONS
