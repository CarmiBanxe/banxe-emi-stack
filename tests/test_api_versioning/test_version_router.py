"""Tests for services/api_versioning/version_router.py"""

from services.api_versioning.models import ApiVersion, ApiVersionSpec, VersionStatus
from services.api_versioning.version_router import VERSION_REGISTRY, VersionRouter


def _make_router() -> VersionRouter:
    return VersionRouter()


def test_get_active_versions_returns_non_sunset():
    vr = _make_router()
    specs = vr.get_active_versions()
    assert all(s.status != VersionStatus.SUNSET for s in specs)


def test_get_active_versions_includes_v1():
    vr = _make_router()
    versions = [s.version for s in vr.get_active_versions()]
    assert ApiVersion.V1 in versions


def test_resolve_version_from_accept_version_header():
    vr = _make_router()
    v = vr.resolve_version({"Accept-Version": "v1"})
    assert v == ApiVersion.V1


def test_resolve_version_v2_experimental():
    vr = _make_router()
    v = vr.resolve_version({"Accept-Version": "v2"})
    assert v == ApiVersion.V2


def test_resolve_version_fallback_to_v1():
    vr = _make_router()
    v = vr.resolve_version({})
    assert v == ApiVersion.V1


def test_resolve_version_unknown_header_fallback():
    vr = _make_router()
    v = vr.resolve_version({"Accept-Version": "v99"})
    assert v == ApiVersion.V1  # fallback


def test_resolve_version_from_x_api_version_header():
    vr = _make_router()
    v = vr.resolve_version({"X-API-Version": "v1"})
    assert v == ApiVersion.V1


def test_is_version_supported_v1():
    vr = _make_router()
    assert vr.is_version_supported("v1") is True


def test_is_version_supported_v2():
    vr = _make_router()
    assert vr.is_version_supported("v2") is True


def test_is_version_supported_unknown():
    vr = _make_router()
    assert vr.is_version_supported("v99") is False


def test_is_version_supported_sunset():
    vr = _make_router()
    spec = ApiVersionSpec(
        version=ApiVersion.V1,
        status=VersionStatus.SUNSET,
        release_date="2025-01-01",
        sunset_date="2026-01-01",
    )
    vr.register_version(spec)
    assert vr.is_version_supported("v1") is False


def test_add_sunset_header_no_sunset_date():
    vr = _make_router()
    headers: dict[str, str] = {}
    result = vr.add_sunset_header("v1", headers)
    assert "Sunset" not in result


def test_add_sunset_header_with_sunset_date():
    vr = _make_router()
    spec = ApiVersionSpec(
        version=ApiVersion.V1,
        status=VersionStatus.DEPRECATED,
        release_date="2025-01-01",
        sunset_date="2027-01-01",
    )
    vr.register_version(spec)
    headers: dict[str, str] = {}
    result = vr.add_sunset_header("v1", headers)
    assert result.get("Sunset") == "2027-01-01"
    assert result.get("Deprecation") == "true"


def test_add_sunset_header_unknown_version():
    vr = _make_router()
    headers: dict[str, str] = {}
    result = vr.add_sunset_header("v99", headers)
    assert headers == result  # unchanged


def test_negotiate_version_valid():
    vr = _make_router()
    result = vr.negotiate_version("v1", "v1")
    assert result == ApiVersion.V1


def test_negotiate_version_too_old():
    vr = _make_router()
    # v1 is older than v2, so if min is v2 and client is v1 → None
    result = vr.negotiate_version("v1", "v2")
    assert result is None


def test_negotiate_version_unknown():
    vr = _make_router()
    result = vr.negotiate_version("v99", "v1")
    assert result is None


def test_version_registry_has_v1_and_v2():
    assert ApiVersion.V1 in VERSION_REGISTRY
    assert ApiVersion.V2 in VERSION_REGISTRY


def test_version_registry_v1_active():
    spec = VERSION_REGISTRY[ApiVersion.V1]
    assert spec.status == VersionStatus.ACTIVE


def test_version_registry_v2_experimental():
    spec = VERSION_REGISTRY[ApiVersion.V2]
    assert spec.status == VersionStatus.EXPERIMENTAL


def test_get_version_spec_existing():
    vr = _make_router()
    spec = vr.get_version_spec("v1")
    assert spec is not None
    assert spec.version == ApiVersion.V1


def test_get_version_spec_missing():
    vr = _make_router()
    spec = vr.get_version_spec("v99")
    assert spec is None


def test_deprecation_notice_days_default_90():
    spec = VERSION_REGISTRY[ApiVersion.V1]
    assert spec.deprecation_notice_days == 90
