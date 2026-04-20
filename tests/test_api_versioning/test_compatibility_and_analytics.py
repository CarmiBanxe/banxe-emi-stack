"""Tests for compatibility_checker.py and version_analytics.py"""

from services.api_versioning.compatibility_checker import CompatibilityChecker
from services.api_versioning.version_analytics import VersionAnalytics

# ── CompatibilityChecker tests ────────────────────────────────────────────────


def test_check_backward_compatible_no_issues():
    cc = CompatibilityChecker()
    s1 = {"properties": {"id": {"type": "string"}, "name": {"type": "string"}}}
    s2 = {
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "new": {"type": "integer"},
        }
    }
    ok, issues = cc.check_backward_compatible(s1, s2)
    assert ok is True
    assert issues == []


def test_check_backward_compatible_field_removed():
    cc = CompatibilityChecker()
    s1 = {"properties": {"id": {"type": "string"}, "old_field": {"type": "string"}}}
    s2 = {"properties": {"id": {"type": "string"}}}
    ok, issues = cc.check_backward_compatible(s1, s2)
    assert ok is False
    assert any("old_field" in i for i in issues)


def test_check_backward_compatible_type_changed():
    cc = CompatibilityChecker()
    s1 = {"properties": {"amount": {"type": "string"}}}
    s2 = {"properties": {"amount": {"type": "number"}}}
    ok, issues = cc.check_backward_compatible(s1, s2)
    assert ok is False
    assert any("amount" in i for i in issues)


def test_detect_field_removals_empty():
    cc = CompatibilityChecker()
    removals = cc.detect_field_removals({}, {})
    assert removals == []


def test_detect_field_removals_identifies_missing():
    cc = CompatibilityChecker()
    old = {"properties": {"a": {}, "b": {}}}
    new = {"properties": {"a": {}}}
    removals = cc.detect_field_removals(old, new)
    assert len(removals) == 1
    assert "b" in removals[0]


def test_detect_type_changes_no_change():
    cc = CompatibilityChecker()
    schema = {"properties": {"x": {"type": "string"}}}
    issues = cc.detect_type_changes(schema, schema)
    assert issues == []


def test_detect_type_changes_detects_change():
    cc = CompatibilityChecker()
    old = {"properties": {"x": {"type": "string"}}}
    new = {"properties": {"x": {"type": "integer"}}}
    issues = cc.detect_type_changes(old, new)
    assert len(issues) == 1
    assert "x" in issues[0]


def test_validate_migration_path_forward():
    cc = CompatibilityChecker()
    assert cc.validate_migration_path("v1", "v2") is True


def test_validate_migration_path_backward():
    cc = CompatibilityChecker()
    assert cc.validate_migration_path("v2", "v1") is False


def test_validate_migration_path_same():
    cc = CompatibilityChecker()
    assert cc.validate_migration_path("v1", "v1") is False


def test_validate_migration_path_unknown():
    cc = CompatibilityChecker()
    assert cc.validate_migration_path("v1", "v99") is False


def test_get_compatibility_matrix_structure():
    cc = CompatibilityChecker()
    matrix = cc.get_compatibility_matrix()
    assert "versions" in matrix
    assert "matrix" in matrix
    assert "v1" in matrix["versions"]


def test_assert_no_breaking_changes_active_version():
    cc = CompatibilityChecker()
    issues = cc.assert_no_breaking_changes("v1")
    assert issues == []


def test_assert_no_breaking_changes_unknown():
    cc = CompatibilityChecker()
    issues = cc.assert_no_breaking_changes("v99")
    assert len(issues) > 0


# ── VersionAnalytics tests ────────────────────────────────────────────────────


def test_record_version_usage():
    va = VersionAnalytics()
    va.record_version_usage("v1", "/v1/payments", "ten_abc")
    usage = va.get_usage_by_version()
    assert usage.get("v1", 0) == 1


def test_record_multiple_usages():
    va = VersionAnalytics()
    va.record_version_usage("v1", "/v1/a", "ten_abc")
    va.record_version_usage("v1", "/v1/b", "ten_abc")
    va.record_version_usage("v2", "/v2/a", "ten_abc")
    usage = va.get_usage_by_version()
    assert usage["v1"] == 2
    assert usage["v2"] == 1


def test_get_deprecated_usage_empty():
    va = VersionAnalytics()
    va.record_version_usage("v1", "/v1/pay", "ten_abc")
    # v1 is ACTIVE, not deprecated
    deprecated = va.get_deprecated_usage()
    assert "v1" not in deprecated


def test_generate_migration_pressure_report_structure():
    va = VersionAnalytics()
    report = va.generate_migration_pressure_report()
    assert "deprecated_versions" in report
    assert "tenants_needing_migration" in report


def test_get_sunset_risk_report_structure():
    va = VersionAnalytics()
    report = va.get_sunset_risk_report()
    assert "sunset_versions" in report
    assert "endpoints_at_risk" in report
    assert "affected_tenant_count" in report


def test_get_usage_by_version_empty():
    va = VersionAnalytics()
    usage = va.get_usage_by_version()
    assert usage == {}


def test_get_version_share_empty():
    va = VersionAnalytics()
    share = va.get_version_share()
    assert share == {}


def test_get_version_share_sums_to_100():
    va = VersionAnalytics()
    va.record_version_usage("v1", "/v1/a", "ten_abc")
    va.record_version_usage("v1", "/v1/b", "ten_abc")
    va.record_version_usage("v2", "/v2/a", "ten_abc")
    share = va.get_version_share()
    total = sum(share.values())
    assert abs(total - 100.0) < 0.01


def test_record_usage_multiple_tenants():
    va = VersionAnalytics()
    va.record_version_usage("v1", "/v1/pay", "ten_a")
    va.record_version_usage("v1", "/v1/pay", "ten_b")
    usage = va.get_usage_by_version()
    assert usage["v1"] == 2
