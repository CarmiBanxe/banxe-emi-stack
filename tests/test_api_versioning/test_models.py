"""Tests for services/api_versioning/models.py"""

import pytest

from services.api_versioning.models import (
    ApiVersion,
    ApiVersionSpec,
    BreakingChange,
    BreakingChangeType,
    DeprecationNotice,
    HITLProposal,
    VersionStatus,
)


def test_api_version_enum_values():
    assert ApiVersion.V1 == "v1"
    assert ApiVersion.V2 == "v2"
    assert ApiVersion.V3 == "v3"


def test_version_status_enum_values():
    assert VersionStatus.ACTIVE == "active"
    assert VersionStatus.DEPRECATED == "deprecated"
    assert VersionStatus.SUNSET == "sunset"
    assert VersionStatus.EXPERIMENTAL == "experimental"


def test_breaking_change_type_enum_values():
    assert BreakingChangeType.FIELD_REMOVED == "field_removed"
    assert BreakingChangeType.ENDPOINT_REMOVED == "endpoint_removed"
    assert BreakingChangeType.AUTH_CHANGED == "auth_changed"


def test_api_version_spec_frozen():
    spec = ApiVersionSpec(
        version=ApiVersion.V1,
        status=VersionStatus.ACTIVE,
        release_date="2025-01-01",
        sunset_date=None,
    )
    with pytest.raises(AttributeError):
        spec.status = VersionStatus.DEPRECATED  # type: ignore


def test_api_version_spec_defaults():
    spec = ApiVersionSpec(
        version=ApiVersion.V1,
        status=VersionStatus.ACTIVE,
        release_date="2025-01-01",
        sunset_date=None,
    )
    assert spec.deprecation_notice_days == 90
    assert spec.changelog_url is None


def test_breaking_change_frozen():
    bc = BreakingChange(
        change_id="chg_001",
        version_from=ApiVersion.V1,
        version_to=ApiVersion.V2,
        change_type=BreakingChangeType.FIELD_REMOVED,
        endpoint="/v1/payments",
        description="Removed 'currency_code'",
        migration_guide="Use 'currency' instead",
        introduced_at="2026-01-01T00:00:00+00:00",
    )
    with pytest.raises(AttributeError):
        bc.endpoint = "changed"  # type: ignore


def test_deprecation_notice_frozen():
    n = DeprecationNotice(
        notice_id="dep_001",
        version=ApiVersion.V1,
        endpoint="/v1/legacy",
        sunset_date="2027-01-01",
        migration_endpoint="/v2/legacy",
        created_at="2026-01-01T00:00:00+00:00",
    )
    with pytest.raises(AttributeError):
        n.endpoint = "changed"  # type: ignore


def test_hitl_proposal_defaults():
    p = HITLProposal(
        action="trigger_sunset",
        version="v1",
        requires_approval_from="API_GOV",
        reason="sunset broadcast",
    )
    assert p.autonomy_level == "L4"


def test_hitl_proposal_mutable():
    p = HITLProposal(
        action="trigger_sunset",
        version="v1",
        requires_approval_from="API_GOV",
        reason="test",
    )
    p.autonomy_level = "L3"
    assert p.autonomy_level == "L3"


def test_api_version_from_string():
    v = ApiVersion("v1")
    assert v == ApiVersion.V1


def test_version_status_from_string():
    s = VersionStatus("deprecated")
    assert s == VersionStatus.DEPRECATED


def test_breaking_change_type_from_string():
    t = BreakingChangeType("field_removed")
    assert t == BreakingChangeType.FIELD_REMOVED
