"""
services/api_versioning/changelog_generator.py — Breaking change log and migration guides
IL-AVD-01 | Phase 44 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import UTC, datetime
import uuid

from services.api_versioning.models import (
    ApiVersion,
    BreakingChange,
    BreakingChangeType,
)


class ChangelogGenerator:
    """Records breaking changes and generates migration documentation."""

    def __init__(self) -> None:
        self._changes: list[BreakingChange] = []

    def record_breaking_change(
        self,
        version_from: str,
        version_to: str,
        change_type: str,
        endpoint: str,
        description: str,
        migration_guide: str,
    ) -> BreakingChange:
        """Record a breaking change between versions."""
        change = BreakingChange(
            change_id=f"chg_{uuid.uuid4().hex[:8]}",
            version_from=ApiVersion(version_from.lower()),
            version_to=ApiVersion(version_to.lower()),
            change_type=BreakingChangeType(change_type),
            endpoint=endpoint,
            description=description,
            migration_guide=migration_guide,
            introduced_at=datetime.now(UTC).isoformat(),
        )
        self._changes.append(change)
        return change

    def generate_changelog(self, version_from: str, version_to: str) -> str:
        """Generate markdown changelog between two versions."""
        changes = self._filter_changes(version_from, version_to)
        if not changes:
            return f"# Changelog {version_from} → {version_to}\n\nNo breaking changes.\n"
        lines = [
            f"# Changelog {version_from} → {version_to}",
            f"\nGenerated: {datetime.now(UTC).date().isoformat()}\n",
            "## Breaking Changes\n",
        ]
        for c in changes:
            lines.append(f"### [{c.change_type.value}] {c.endpoint}")
            lines.append(f"\n{c.description}\n")
            lines.append(f"**Migration:** {c.migration_guide}\n")
        return "\n".join(lines)

    def get_breaking_changes(self, version: str) -> list[BreakingChange]:
        """Get all breaking changes for a specific version (as source)."""
        return [c for c in self._changes if c.version_from.value == version]

    def generate_migration_guide(self, version_from: str, version_to: str) -> dict:
        """Generate structured migration guide between versions."""
        changes = self._filter_changes(version_from, version_to)
        return {
            "from_version": version_from,
            "to_version": version_to,
            "total_changes": len(changes),
            "steps": [
                {
                    "endpoint": c.endpoint,
                    "change_type": c.change_type.value,
                    "guide": c.migration_guide,
                }
                for c in changes
            ],
        }

    def get_change_summary(self) -> dict:
        """Get stats: total changes, by type, by version."""
        by_type: dict[str, int] = {}
        by_version: dict[str, int] = {}
        for c in self._changes:
            by_type[c.change_type.value] = by_type.get(c.change_type.value, 0) + 1
            key = f"{c.version_from.value}→{c.version_to.value}"
            by_version[key] = by_version.get(key, 0) + 1
        return {
            "total_changes": len(self._changes),
            "by_type": by_type,
            "by_version_pair": by_version,
        }

    def export_openapi_diff(self, version_from: str, version_to: str) -> dict:
        """Export breaking changes as OpenAPI-diff-like format."""
        changes = self._filter_changes(version_from, version_to)
        return {
            "version_from": version_from,
            "version_to": version_to,
            "breaking": [
                {
                    "id": c.change_id,
                    "type": c.change_type.value,
                    "path": c.endpoint,
                    "description": c.description,
                }
                for c in changes
            ],
        }

    def _filter_changes(self, version_from: str, version_to: str) -> list[BreakingChange]:
        return [
            c
            for c in self._changes
            if c.version_from.value == version_from and c.version_to.value == version_to
        ]
