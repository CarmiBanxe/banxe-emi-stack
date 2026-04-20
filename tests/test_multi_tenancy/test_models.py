"""Tests for services/multi_tenancy/models.py"""

from decimal import Decimal

import pytest

from services.multi_tenancy.models import (
    HITLProposal,
    InMemoryQuotaPort,
    InMemoryTenantAuditPort,
    InMemoryTenantPort,
    IsolationLevel,
    Tenant,
    TenantAuditEntry,
    TenantContext,
    TenantQuota,
    TenantStatus,
    TenantTier,
)


def _make_tenant(
    tenant_id: str = "ten_abc123", status: TenantStatus = TenantStatus.ACTIVE
) -> Tenant:
    return Tenant(
        tenant_id=tenant_id,
        name="Acme Corp",
        tier=TenantTier.BUSINESS,
        status=status,
        isolation_level=IsolationLevel.SCHEMA,
        monthly_fee=Decimal("99.00"),
        daily_tx_limit=10000,
        jurisdiction="GB",
        kyb_verified=True,
        cass_pool_id=f"pool_{tenant_id}",
    )


def test_tenant_frozen():
    t = _make_tenant()
    with pytest.raises(AttributeError):
        t.name = "changed"  # type: ignore


def test_tenant_monthly_fee_is_decimal():
    t = _make_tenant()
    assert isinstance(t.monthly_fee, Decimal)


def test_tenant_status_enum_values():
    assert TenantStatus.ACTIVE == "active"
    assert TenantStatus.SUSPENDED == "suspended"
    assert TenantStatus.TERMINATED == "terminated"
    assert TenantStatus.PENDING_KYB == "pending_kyb"


def test_tenant_tier_enum_values():
    assert TenantTier.BASIC == "basic"
    assert TenantTier.BUSINESS == "business"
    assert TenantTier.ENTERPRISE == "enterprise"


def test_isolation_level_enum_values():
    assert IsolationLevel.SHARED == "shared"
    assert IsolationLevel.SCHEMA == "schema"
    assert IsolationLevel.DEDICATED == "dedicated"


def test_tenant_context_frozen():
    ctx = TenantContext(
        tenant_id="ten_abc",
        user_id="u001",
        scopes=["read", "write"],
        request_id="req-001",
    )
    with pytest.raises(AttributeError):
        ctx.tenant_id = "changed"  # type: ignore


def test_tenant_quota_decimal_fields():
    q = TenantQuota(
        tenant_id="ten_abc",
        daily_tx_used=100,
        daily_tx_limit=1000,
        monthly_volume_gbp=Decimal("1234.56"),
        monthly_volume_limit_gbp=Decimal("50000.00"),
    )
    assert isinstance(q.monthly_volume_gbp, Decimal)
    assert isinstance(q.monthly_volume_limit_gbp, Decimal)


def test_tenant_audit_entry_frozen():
    e = TenantAuditEntry(
        entry_id="e001",
        tenant_id="ten_abc",
        action="CREATED",
        actor="admin",
        timestamp="2026-04-20T00:00:00+00:00",
        details={"key": "val"},
    )
    with pytest.raises(AttributeError):
        e.action = "MODIFIED"  # type: ignore


def test_hitl_proposal_defaults():
    p = HITLProposal(
        action="provision",
        tenant_id="ten_abc",
        requires_approval_from="MLRO",
        reason="test",
    )
    assert p.autonomy_level == "L4"


def test_in_memory_tenant_port_save_and_get():
    port = InMemoryTenantPort()
    t = _make_tenant("ten_001")
    port.save(t)
    result = port.get("ten_001")
    assert result is not None
    assert result.name == "Acme Corp"


def test_in_memory_tenant_port_get_missing():
    port = InMemoryTenantPort()
    assert port.get("missing") is None


def test_in_memory_tenant_port_list_active():
    port = InMemoryTenantPort()
    port.save(_make_tenant("ten_001", TenantStatus.ACTIVE))
    port.save(_make_tenant("ten_002", TenantStatus.SUSPENDED))
    active = port.list_active()
    assert len(active) == 1
    assert active[0].tenant_id == "ten_001"


def test_in_memory_audit_port_append_only():
    port = InMemoryTenantAuditPort()
    e = TenantAuditEntry("e1", "ten_abc", "ACT", "admin", "2026-04-20", {})
    port.append(e)
    entries = port.list_by_tenant("ten_abc")
    assert len(entries) == 1


def test_in_memory_audit_port_no_delete():
    """I-24: audit port has no delete method."""
    port = InMemoryTenantAuditPort()
    assert not hasattr(port, "delete")
    assert not hasattr(port, "remove")


def test_in_memory_audit_port_list_by_tenant_filter():
    port = InMemoryTenantAuditPort()
    port.append(TenantAuditEntry("e1", "ten_a", "A1", "admin", "2026-04-20", {}))
    port.append(TenantAuditEntry("e2", "ten_b", "A2", "admin", "2026-04-20", {}))
    port.append(TenantAuditEntry("e3", "ten_a", "A3", "admin", "2026-04-20", {}))
    result = port.list_by_tenant("ten_a")
    assert len(result) == 2


def test_in_memory_quota_port_save_and_get():
    port = InMemoryQuotaPort()
    q = TenantQuota("ten_abc", 0, 1000, Decimal("0"), Decimal("50000"))
    port.save(q)
    result = port.get("ten_abc")
    assert result is not None
    assert result.daily_tx_limit == 1000
