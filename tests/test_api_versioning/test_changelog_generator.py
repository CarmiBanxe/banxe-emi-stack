"""Tests for services/api_versioning/changelog_generator.py"""

import pytest

from services.api_versioning.changelog_generator import ChangelogGenerator


def test_record_breaking_change():
    gen = ChangelogGenerator()
    change = gen.record_breaking_change(
        "v1", "v2", "field_removed", "/v1/payments", "Removed 'currency_code'", "Use 'currency'"
    )
    assert change.change_id.startswith("chg_")
    assert change.endpoint == "/v1/payments"


def test_record_breaking_change_invalid_version_raises():
    gen = ChangelogGenerator()
    with pytest.raises(ValueError):
        gen.record_breaking_change("v99", "v2", "field_removed", "/v1/test", "desc", "guide")


def test_record_breaking_change_invalid_type_raises():
    gen = ChangelogGenerator()
    with pytest.raises(ValueError):
        gen.record_breaking_change("v1", "v2", "invalid_type", "/v1/test", "desc", "guide")


def test_generate_changelog_empty():
    gen = ChangelogGenerator()
    md = gen.generate_changelog("v1", "v2")
    assert "No breaking changes" in md


def test_generate_changelog_with_changes():
    gen = ChangelogGenerator()
    gen.record_breaking_change("v1", "v2", "field_removed", "/v1/pay", "Removed fee", "Use fee_v2")
    md = gen.generate_changelog("v1", "v2")
    assert "/v1/pay" in md
    assert "field_removed" in md
    assert "Removed fee" in md


def test_generate_changelog_is_markdown():
    gen = ChangelogGenerator()
    md = gen.generate_changelog("v1", "v2")
    assert md.startswith("# Changelog")


def test_get_breaking_changes_by_version():
    gen = ChangelogGenerator()
    gen.record_breaking_change("v1", "v2", "endpoint_removed", "/v1/old", "Gone", "Use /v2")
    gen.record_breaking_change("v2", "v3", "field_removed", "/v2/test", "Removed", "Use v3")
    v1_changes = gen.get_breaking_changes("v1")
    assert len(v1_changes) == 1
    assert v1_changes[0].endpoint == "/v1/old"


def test_get_breaking_changes_empty():
    gen = ChangelogGenerator()
    changes = gen.get_breaking_changes("v1")
    assert changes == []


def test_generate_migration_guide_structure():
    gen = ChangelogGenerator()
    gen.record_breaking_change("v1", "v2", "field_removed", "/v1/pay", "Removed", "Use v2")
    guide = gen.generate_migration_guide("v1", "v2")
    assert guide["from_version"] == "v1"
    assert guide["to_version"] == "v2"
    assert guide["total_changes"] == 1
    assert len(guide["steps"]) == 1


def test_generate_migration_guide_empty():
    gen = ChangelogGenerator()
    guide = gen.generate_migration_guide("v1", "v2")
    assert guide["total_changes"] == 0
    assert guide["steps"] == []


def test_get_change_summary_empty():
    gen = ChangelogGenerator()
    summary = gen.get_change_summary()
    assert summary["total_changes"] == 0


def test_get_change_summary_counts():
    gen = ChangelogGenerator()
    gen.record_breaking_change("v1", "v2", "field_removed", "/v1/a", "d", "m")
    gen.record_breaking_change("v1", "v2", "endpoint_removed", "/v1/b", "d", "m")
    gen.record_breaking_change("v2", "v3", "field_type_changed", "/v2/a", "d", "m")
    summary = gen.get_change_summary()
    assert summary["total_changes"] == 3
    assert summary["by_type"]["field_removed"] == 1
    assert summary["by_type"]["endpoint_removed"] == 1
    assert summary["by_version_pair"]["v1→v2"] == 2
    assert summary["by_version_pair"]["v2→v3"] == 1


def test_export_openapi_diff_structure():
    gen = ChangelogGenerator()
    gen.record_breaking_change("v1", "v2", "field_removed", "/v1/pay", "desc", "guide")
    diff = gen.export_openapi_diff("v1", "v2")
    assert diff["version_from"] == "v1"
    assert diff["version_to"] == "v2"
    assert len(diff["breaking"]) == 1
    assert diff["breaking"][0]["type"] == "field_removed"


def test_change_introduced_at_is_set():
    gen = ChangelogGenerator()
    change = gen.record_breaking_change("v1", "v2", "field_removed", "/v1/test", "d", "m")
    assert change.introduced_at is not None
    assert "T" in change.introduced_at
