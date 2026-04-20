"""
services/api_versioning/compatibility_checker.py — Backward compatibility analysis
IL-AVD-01 | Phase 44 | banxe-emi-stack
"""

from __future__ import annotations

from services.api_versioning.models import ApiVersion, VersionStatus
from services.api_versioning.version_router import VERSION_REGISTRY


class CompatibilityChecker:
    """Checks backward compatibility between API schema versions."""

    def __init__(self) -> None:
        self._registry = dict(VERSION_REGISTRY)

    def check_backward_compatible(self, schema_v1: dict, schema_v2: dict) -> tuple[bool, list[str]]:
        """Check if schema_v2 is backward compatible with schema_v1."""
        issues: list[str] = []
        removals = self.detect_field_removals(schema_v1, schema_v2)
        issues.extend(removals)
        type_changes = self.detect_type_changes(schema_v1, schema_v2)
        issues.extend(type_changes)
        return len(issues) == 0, issues

    def detect_field_removals(self, old_schema: dict, new_schema: dict) -> list[str]:
        """Detect fields present in old schema but missing in new schema."""
        old_fields = set(old_schema.get("properties", {}).keys())
        new_fields = set(new_schema.get("properties", {}).keys())
        removed = old_fields - new_fields
        return [f"Field removed: '{f}'" for f in sorted(removed)]

    def detect_type_changes(self, old_schema: dict, new_schema: dict) -> list[str]:
        """Detect fields where type changed between schemas."""
        issues: list[str] = []
        old_props = old_schema.get("properties", {})
        new_props = new_schema.get("properties", {})
        for field, old_def in old_props.items():
            if field not in new_props:
                continue  # handled by detect_field_removals
            new_def = new_props[field]
            old_type = old_def.get("type")
            new_type = new_def.get("type")
            if old_type and new_type and old_type != new_type:
                issues.append(f"Type changed for '{field}': {old_type!r} → {new_type!r}")
        return issues

    def validate_migration_path(self, version_from: str, version_to: str) -> bool:
        """Check that a valid migration path exists between versions."""
        try:
            v_from = ApiVersion(version_from.lower())
            v_to = ApiVersion(version_to.lower())
        except ValueError:
            return False
        versions = list(ApiVersion)
        try:
            idx_from = versions.index(v_from)
            idx_to = versions.index(v_to)
        except ValueError:
            return False
        # Forward migration only (no downgrade)
        return idx_to > idx_from

    def get_compatibility_matrix(self) -> dict:
        """Return compatibility matrix for all supported version pairs."""
        versions = [v for v in ApiVersion if v in self._registry]
        matrix: dict[str, dict[str, bool]] = {}
        for v in versions:
            row: dict[str, bool] = {}
            for v2 in versions:
                row[v2.value] = self.validate_migration_path(v.value, v2.value)
            matrix[v.value] = row
        return {
            "versions": [v.value for v in versions],
            "matrix": matrix,
        }

    def assert_no_breaking_changes(self, version: str) -> list[str]:
        """Assert no breaking changes exist for a version. Returns issues."""
        try:
            v = ApiVersion(version.lower())
        except ValueError:
            return [f"Unknown version: {version!r}"]
        spec = self._registry.get(v)
        if spec is None:
            return [f"Version {version!r} not in registry"]
        issues: list[str] = []
        if spec.status == VersionStatus.DEPRECATED:
            issues.append(f"Version {version} is deprecated")
        if spec.status == VersionStatus.SUNSET:
            issues.append(f"Version {version} is sunset")
        return issues
