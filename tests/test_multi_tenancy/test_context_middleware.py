"""Tests for services/multi_tenancy/context_middleware.py"""

from decimal import Decimal

import pytest

from services.multi_tenancy.context_middleware import TenantContextMiddleware
from services.multi_tenancy.models import (
    InMemoryTenantPort,
    IsolationLevel,
    Tenant,
    TenantStatus,
    TenantTier,
)


def _make_active_tenant(tenant_id: str = "ten_abc") -> Tenant:
    return Tenant(
        tenant_id=tenant_id,
        name="TestCo",
        tier=TenantTier.BASIC,
        status=TenantStatus.ACTIVE,
        isolation_level=IsolationLevel.SHARED,
        monthly_fee=Decimal("10.00"),
        daily_tx_limit=1000,
        jurisdiction="GB",
        kyb_verified=True,
        cass_pool_id=f"pool_{tenant_id}",
    )


def test_extract_tenant_context_success():
    mw = TenantContextMiddleware()
    headers = {
        "X-Tenant-ID": "ten_abc",
        "X-User-ID": "user_001",
        "X-Scopes": "read,write",
        "X-Request-ID": "req-xyz",
    }
    ctx = mw.extract_tenant_context(headers)
    assert ctx is not None
    assert ctx.tenant_id == "ten_abc"
    assert ctx.user_id == "user_001"
    assert "read" in ctx.scopes
    assert "write" in ctx.scopes


def test_extract_tenant_context_missing_tenant_id():
    mw = TenantContextMiddleware()
    ctx = mw.extract_tenant_context({"X-User-ID": "user_001"})
    assert ctx is None


def test_extract_tenant_context_default_request_id():
    mw = TenantContextMiddleware()
    ctx = mw.extract_tenant_context({"X-Tenant-ID": "ten_abc"})
    assert ctx is not None
    assert ctx.request_id is not None
    assert len(ctx.request_id) > 0


def test_extract_tenant_context_empty_scopes():
    mw = TenantContextMiddleware()
    ctx = mw.extract_tenant_context({"X-Tenant-ID": "ten_abc"})
    assert ctx is not None
    assert ctx.scopes == []


def test_validate_tenant_active_true():
    port = InMemoryTenantPort()
    port.save(_make_active_tenant("ten_abc"))
    mw = TenantContextMiddleware(tenant_port=port)
    assert mw.validate_tenant_active("ten_abc") is True


def test_validate_tenant_active_missing():
    mw = TenantContextMiddleware()
    assert mw.validate_tenant_active("ten_missing") is False


def test_validate_tenant_active_suspended():
    port = InMemoryTenantPort()
    t = Tenant(
        tenant_id="ten_sus",
        name="SuspendedCo",
        tier=TenantTier.BASIC,
        status=TenantStatus.SUSPENDED,
        isolation_level=IsolationLevel.SHARED,
        monthly_fee=Decimal("10.00"),
        daily_tx_limit=1000,
        jurisdiction="GB",
    )
    port.save(t)
    mw = TenantContextMiddleware(tenant_port=port)
    assert mw.validate_tenant_active("ten_sus") is False


def test_inject_and_get_current_tenant():
    mw = TenantContextMiddleware()
    ctx = mw.inject_tenant_context("ten_abc", "u001", ["read"], "req-001")
    retrieved = mw.get_current_tenant()
    assert retrieved.tenant_id == "ten_abc"


def test_get_current_tenant_raises_if_not_set():
    mw = TenantContextMiddleware()
    mw.clear_context()
    with pytest.raises(RuntimeError):
        mw.get_current_tenant()


def test_require_tenant_scope_true():
    mw = TenantContextMiddleware()
    mw.inject_tenant_context("ten_abc", "u001", ["read", "write"], "req-001")
    assert mw.require_tenant_scope("read") is True


def test_require_tenant_scope_false():
    mw = TenantContextMiddleware()
    mw.inject_tenant_context("ten_abc", "u001", ["read"], "req-001")
    assert mw.require_tenant_scope("admin") is False


def test_require_tenant_scope_no_context():
    mw = TenantContextMiddleware()
    mw.clear_context()
    assert mw.require_tenant_scope("read") is False


def test_clear_context():
    mw = TenantContextMiddleware()
    mw.inject_tenant_context("ten_abc", "u001", [], "req-001")
    mw.clear_context()
    with pytest.raises(RuntimeError):
        mw.get_current_tenant()


def test_inject_context_returns_context():
    mw = TenantContextMiddleware()
    ctx = mw.inject_tenant_context("ten_xyz", "u002", ["pay"], "req-002")
    assert ctx.tenant_id == "ten_xyz"
    assert "pay" in ctx.scopes
