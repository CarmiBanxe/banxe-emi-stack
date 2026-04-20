"""
services/api_versioning/version_router.py — API version registry and negotiation
IL-AVD-01 | Phase 44 | banxe-emi-stack
RFC 8594: Sunset header support.
"""

from __future__ import annotations

from services.api_versioning.models import (
    ApiVersion,
    ApiVersionSpec,
    DeprecationNotice,
    VersionStatus,
)

VERSION_REGISTRY: dict[ApiVersion, ApiVersionSpec] = {
    ApiVersion.V1: ApiVersionSpec(
        version=ApiVersion.V1,
        status=VersionStatus.ACTIVE,
        release_date="2025-01-01",
        sunset_date=None,
        deprecation_notice_days=90,
    ),
    ApiVersion.V2: ApiVersionSpec(
        version=ApiVersion.V2,
        status=VersionStatus.EXPERIMENTAL,
        release_date="2026-01-01",
        sunset_date=None,
        deprecation_notice_days=90,
    ),
}


class VersionRouter:
    """Manages API version resolution and sunset header injection."""

    def __init__(
        self,
        registry: dict[ApiVersion, ApiVersionSpec] | None = None,
    ) -> None:
        self._registry: dict[ApiVersion, ApiVersionSpec] = registry or dict(VERSION_REGISTRY)
        # Deprecation notices keyed by (version, endpoint)
        self._deprecations: dict[tuple[str, str], DeprecationNotice] = {}

    def get_active_versions(self) -> list[ApiVersionSpec]:
        """Return all non-sunset versions."""
        return [spec for spec in self._registry.values() if spec.status != VersionStatus.SUNSET]

    def resolve_version(self, request_headers: dict[str, str]) -> ApiVersion:
        """Resolve API version from Accept-Version header or URL prefix."""
        version_header = request_headers.get("Accept-Version", "").strip()
        if version_header:
            try:
                return ApiVersion(version_header.lower())
            except ValueError:
                pass
        # Check X-API-Version as alternative
        alt = request_headers.get("X-API-Version", "").strip()
        if alt:
            try:
                return ApiVersion(alt.lower())
            except ValueError:
                pass
        return ApiVersion.V1  # default

    def is_version_supported(self, version: str) -> bool:
        """Check if a version string is a supported (non-sunset) version."""
        try:
            v = ApiVersion(version.lower())
        except ValueError:
            return False
        spec = self._registry.get(v)
        return spec is not None and spec.status != VersionStatus.SUNSET

    def get_deprecation_info(self, version: str) -> DeprecationNotice | None:
        """Get deprecation notice for a version, if any."""
        for (v, _), notice in self._deprecations.items():
            if v == version:
                return notice
        return None

    def add_sunset_header(self, version: str, response_headers: dict[str, str]) -> dict[str, str]:
        """RFC 8594: inject Sunset header if version has a sunset date."""
        try:
            v = ApiVersion(version.lower())
        except ValueError:
            return response_headers
        spec = self._registry.get(v)
        if spec and spec.sunset_date:
            response_headers["Sunset"] = spec.sunset_date
            response_headers["Deprecation"] = "true"
        return response_headers

    def negotiate_version(self, client_version: str, min_supported: str) -> ApiVersion | None:
        """Negotiate best supported version >= min_supported."""
        try:
            client_v = ApiVersion(client_version.lower())
        except ValueError:
            return None
        if not self.is_version_supported(client_version):
            return None
        versions = list(ApiVersion)
        try:
            min_idx = versions.index(ApiVersion(min_supported.lower()))
            client_idx = versions.index(client_v)
        except ValueError:
            return None
        if client_idx < min_idx:
            return None
        return client_v

    def register_version(self, spec: ApiVersionSpec) -> None:
        """Register a new version spec in the registry."""
        self._registry[spec.version] = spec

    def get_version_spec(self, version: str) -> ApiVersionSpec | None:
        """Get version spec by version string."""
        try:
            v = ApiVersion(version.lower())
        except ValueError:
            return None
        return self._registry.get(v)
