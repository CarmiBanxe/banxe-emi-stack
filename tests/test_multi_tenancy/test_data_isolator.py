"""Tests for services/multi_tenancy/data_isolator.py"""

from decimal import Decimal

import pytest

from services.multi_tenancy.data_isolator import DataIsolator
from services.multi_tenancy.models import (
    InMemoryTenantAuditPort,
    InMemoryTenantPort,
    IsolationLevel,
    Tenant,
    TenantStatus,
    TenantTier,
)


def _make_tenant(tenant_id: str, isolation: IsolationLevel) -> Tenant:
    return Tenant(
        tenant_id=tenant_id,
        name="TestCo",
        tier=TenantTier.BUSINESS,
        status=TenantStatus.ACTIVE,
        isolation_level=isolation,
        monthly_fee=Decimal("99.00"),
        daily_tx_limit=10000,
        jurisdiction="GB",
    )


def _make_isolator(tenant_id: str, isolation: IsolationLevel) -> DataIsolator:
    tp = InMemoryTenantPort()
    tp.save(_make_tenant(tenant_id, isolation))
    ap = InMemoryTenantAuditPort()
    return DataIsolator(tenant_port=tp, audit_port=ap)


def test_get_tenant_schema_shared():
    iso = _make_isolator("ten_abc", IsolationLevel.SHARED)
    assert iso.get_tenant_schema("ten_abc") == "public"


def test_get_tenant_schema_schema():
    iso = _make_isolator("ten_abc", IsolationLevel.SCHEMA)
    schema = iso.get_tenant_schema("ten_abc")
    assert schema == "tenant_ten_abc"


def test_get_tenant_schema_dedicated():
    iso = _make_isolator("ten_abc", IsolationLevel.DEDICATED)
    schema = iso.get_tenant_schema("ten_abc")
    assert "ten_abc" in schema
    assert "dedicated" in schema


def test_get_tenant_schema_missing():
    iso = DataIsolator()
    with pytest.raises(ValueError):
        iso.get_tenant_schema("ten_missing")


def test_get_connection_pool_shared():
    iso = _make_isolator("ten_abc", IsolationLevel.SHARED)
    pool = iso.get_connection_pool("ten_abc")
    assert pool == "pool_shared"


def test_get_connection_pool_schema():
    iso = _make_isolator("ten_abc", IsolationLevel.SCHEMA)
    pool = iso.get_connection_pool("ten_abc")
    assert "ten_abc" in pool


def test_get_connection_pool_dedicated():
    iso = _make_isolator("ten_abc", IsolationLevel.DEDICATED)
    pool = iso.get_connection_pool("ten_abc")
    assert "dedicated" in pool
    assert "ten_abc" in pool


def test_validate_cross_tenant_access_same_tenant():
    iso = DataIsolator()
    assert iso.validate_cross_tenant_access("ten_a", "ten_a") is True


def test_validate_cross_tenant_access_different_tenants():
    iso = DataIsolator()
    assert iso.validate_cross_tenant_access("ten_a", "ten_b") is False


def test_validate_cross_tenant_access_with_explicit_grant():
    iso = DataIsolator()
    iso.grant_cross_tenant_access("ten_a", "ten_b")
    assert iso.validate_cross_tenant_access("ten_a", "ten_b") is True
    # Reverse should still be False
    assert iso.validate_cross_tenant_access("ten_b", "ten_a") is False


def test_create_row_filter():
    iso = DataIsolator()
    filt = iso.create_row_filter("ten_abc")
    assert filt == {"tenant_id": "ten_abc"}


def test_audit_access_writes_entry():
    tp = InMemoryTenantPort()
    tp.save(_make_tenant("ten_abc", IsolationLevel.SHARED))
    ap = InMemoryTenantAuditPort()
    iso = DataIsolator(tenant_port=tp, audit_port=ap)
    iso.audit_access("ten_abc", "payments", "admin")
    entries = ap.list_by_tenant("ten_abc")
    assert len(entries) == 1
    assert entries[0].action == "DATA_ACCESS"


def test_get_isolation_level_returns_correct():
    iso = _make_isolator("ten_abc", IsolationLevel.SCHEMA)
    level = iso.get_isolation_level("ten_abc")
    assert level == IsolationLevel.SCHEMA


def test_get_isolation_level_missing():
    iso = DataIsolator()
    # DataIsolator with empty port returns None for missing tenant
    result = iso.get_isolation_level("ten_missing")
    assert result is None
