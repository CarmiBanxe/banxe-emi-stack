"""
services/api_versioning/version_analytics.py — API version usage tracking
IL-AVD-01 | Phase 44 | banxe-emi-stack
"""

from __future__ import annotations

from services.api_versioning.models import VersionStatus
from services.api_versioning.version_router import VERSION_REGISTRY


class VersionAnalytics:
    """Tracks API version usage and generates migration pressure reports."""

    def __init__(self) -> None:
        # {version: count}
        self._usage: dict[str, int] = {}
        # {(version, endpoint, tenant_id): count}
        self._detail: dict[tuple[str, str, str], int] = {}
        self._registry = dict(VERSION_REGISTRY)

    def record_version_usage(self, version: str, endpoint: str, tenant_id: str) -> None:
        """Record a single API call for version/endpoint/tenant."""
        self._usage[version] = self._usage.get(version, 0) + 1
        key = (version, endpoint, tenant_id)
        self._detail[key] = self._detail.get(key, 0) + 1

    def get_usage_by_version(self) -> dict[str, int]:
        """Return total call count per version."""
        return dict(self._usage)

    def get_deprecated_usage(self) -> dict:
        """Return usage of deprecated or sunset endpoints."""
        deprecated_versions = {
            v.value
            for v, spec in self._registry.items()
            if spec.status in (VersionStatus.DEPRECATED, VersionStatus.SUNSET)
        }
        result: dict[str, int] = {}
        for version, count in self._usage.items():
            if version in deprecated_versions:
                result[version] = count
        return result

    def generate_migration_pressure_report(self) -> dict:
        """Report which tenants still using deprecated versions."""
        deprecated_versions = {
            v.value
            for v, spec in self._registry.items()
            if spec.status in (VersionStatus.DEPRECATED, VersionStatus.SUNSET)
        }
        tenants_by_version: dict[str, set[str]] = {}
        for (version, endpoint, tenant_id), count in self._detail.items():
            if version in deprecated_versions:
                if version not in tenants_by_version:
                    tenants_by_version[version] = set()
                tenants_by_version[version].add(tenant_id)
        return {
            "deprecated_versions": list(deprecated_versions),
            "tenants_needing_migration": {
                v: list(tenants) for v, tenants in tenants_by_version.items()
            },
        }

    def get_sunset_risk_report(self) -> dict:
        """Report endpoints at risk + affected tenants."""
        sunset_versions = {
            v.value for v, spec in self._registry.items() if spec.status == VersionStatus.SUNSET
        }
        endpoints_at_risk: dict[str, list[str]] = {}
        for version, endpoint, tenant_id in self._detail:
            if version in sunset_versions:
                if endpoint not in endpoints_at_risk:
                    endpoints_at_risk[endpoint] = []
                if tenant_id not in endpoints_at_risk[endpoint]:
                    endpoints_at_risk[endpoint].append(tenant_id)
        return {
            "sunset_versions": list(sunset_versions),
            "endpoints_at_risk": endpoints_at_risk,
            "affected_tenant_count": sum(len(t) for t in endpoints_at_risk.values()),
        }

    def get_version_share(self) -> dict:
        """Return percentage share per version."""
        total = sum(self._usage.values())
        if total == 0:
            return {}
        return {v: round(c / total * 100, 2) for v, c in self._usage.items()}
