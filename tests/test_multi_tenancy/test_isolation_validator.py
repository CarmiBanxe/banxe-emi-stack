"""Tests for services/multi_tenancy/isolation_validator.py"""

from decimal import Decimal

from services.multi_tenancy.isolation_validator import IsolationValidator
from services.multi_tenancy.models import (
    InMemoryTenantPort,
    IsolationLevel,
    Tenant,
    TenantStatus,
    TenantTier,
)


def _make_active_tenant(tenant_id: str, cass_pool_id: str | None = None) -> Tenant:
    return Tenant(
        tenant_id=tenant_id,
        name="ValidateCo",
        tier=TenantTier.BUSINESS,
        status=TenantStatus.ACTIVE,
        isolation_level=IsolationLevel.SCHEMA,
        monthly_fee=Decimal("99.00"),
        daily_tx_limit=10000,
        jurisdiction="GB",
        cass_pool_id=cass_pool_id or f"pool_{tenant_id}",
    )


def _make_validator(
    tenant_id: str = "ten_abc", cass_pool_id: str | None = None
) -> IsolationValidator:
    tp = InMemoryTenantPort()
    tp.save(_make_active_tenant(tenant_id, cass_pool_id))
    return IsolationValidator(tenant_port=tp)


def test_validate_request_isolation_same_tenant():
    v = IsolationValidator()
    assert v.validate_request_isolation("ten_a", "ten_a") is True


def test_validate_request_isolation_different_tenants():
    v = IsolationValidator()
    assert v.validate_request_isolation("ten_a", "ten_b") is False


def test_check_data_leakage_no_leak():
    v = IsolationValidator()
    warnings = v.check_data_leakage({"tenant_id": "ten_a", "data": "ok"}, "ten_a")
    assert warnings == []


def test_check_data_leakage_top_level():
    v = IsolationValidator()
    warnings = v.check_data_leakage({"tenant_id": "ten_b", "data": "ok"}, "ten_a")
    assert len(warnings) == 1
    assert "mismatch" in warnings[0]


def test_check_data_leakage_in_items():
    v = IsolationValidator()
    data = {
        "tenant_id": "ten_a",
        "items": [{"tenant_id": "ten_b", "x": 1}],
    }
    warnings = v.check_data_leakage(data, "ten_a")
    assert len(warnings) == 1
    assert "items[0]" in warnings[0]


def test_check_data_leakage_no_tenant_in_response():
    v = IsolationValidator()
    warnings = v.check_data_leakage({"data": "ok"}, "ten_a")
    assert warnings == []


def test_validate_cass_pool_separation_ok():
    v = _make_validator("ten_abc")
    assert v.validate_cass_pool_separation("ten_abc") is True


def test_validate_cass_pool_separation_missing_pool():
    tp = InMemoryTenantPort()
    t = Tenant(
        tenant_id="ten_nopool",
        name="NoCASS",
        tier=TenantTier.BASIC,
        status=TenantStatus.ACTIVE,
        isolation_level=IsolationLevel.SHARED,
        monthly_fee=Decimal("10.00"),
        daily_tx_limit=1000,
        jurisdiction="GB",
        cass_pool_id=None,
    )
    tp.save(t)
    v = IsolationValidator(tenant_port=tp)
    assert v.validate_cass_pool_separation("ten_nopool") is False


def test_validate_cass_pool_separation_inactive_tenant():
    tp = InMemoryTenantPort()
    t = Tenant(
        tenant_id="ten_sus",
        name="Suspended",
        tier=TenantTier.BASIC,
        status=TenantStatus.SUSPENDED,
        isolation_level=IsolationLevel.SHARED,
        monthly_fee=Decimal("10.00"),
        daily_tx_limit=1000,
        jurisdiction="GB",
        cass_pool_id="pool_ten_sus",
    )
    tp.save(t)
    v = IsolationValidator(tenant_port=tp)
    assert v.validate_cass_pool_separation("ten_sus") is False


def test_validate_cass_pool_separation_missing_tenant():
    v = IsolationValidator()
    assert v.validate_cass_pool_separation("ten_missing") is False


def test_generate_isolation_report_fields():
    v = _make_validator("ten_abc")
    report = v.generate_isolation_report("ten_abc")
    assert report["tenant_id"] == "ten_abc"
    assert "isolation_level" in report
    assert "cass_compliant" in report


def test_generate_isolation_report_missing():
    v = IsolationValidator()
    report = v.generate_isolation_report("ten_missing")
    assert "error" in report


def test_assert_gdpr_data_residence_gb():
    v = _make_validator("ten_abc")
    assert v.assert_gdpr_data_residence("ten_abc", "GB") is True


def test_assert_gdpr_data_residence_invalid_region():
    v = _make_validator("ten_abc")
    assert v.assert_gdpr_data_residence("ten_abc", "US") is False


def test_assert_gdpr_data_residence_blocked_jurisdiction():
    tp = InMemoryTenantPort()
    t = Tenant(
        tenant_id="ten_ru",
        name="RuCo",
        tier=TenantTier.BASIC,
        status=TenantStatus.ACTIVE,
        isolation_level=IsolationLevel.SHARED,
        monthly_fee=Decimal("10.00"),
        daily_tx_limit=1000,
        jurisdiction="RU",
    )
    tp.save(t)
    v = IsolationValidator(tenant_port=tp)
    assert v.assert_gdpr_data_residence("ten_ru", "GB") is False


def test_assert_gdpr_data_residence_missing_tenant():
    v = IsolationValidator()
    assert v.assert_gdpr_data_residence("ten_missing", "GB") is False


def test_get_isolation_level():
    v = _make_validator("ten_abc")
    level = v.get_isolation_level("ten_abc")
    assert level == IsolationLevel.SCHEMA
