"""Tests for services/api_versioning/deprecation_manager.py"""

from datetime import UTC, datetime, timedelta

import pytest

from services.api_versioning.deprecation_manager import DeprecationManager
from services.api_versioning.models import ApiVersion, HITLProposal


def _future_date(days: int = 90) -> str:
    return (datetime.now(UTC).date() + timedelta(days=days)).isoformat()


def _past_date(days: int = 10) -> str:
    return (datetime.now(UTC).date() - timedelta(days=days)).isoformat()


def test_mark_deprecated_creates_notice():
    dm = DeprecationManager()
    notice = dm.mark_deprecated("v1", "/v1/payments", _future_date(), "/v2/payments", "admin")
    assert notice.notice_id.startswith("dep_")
    assert notice.endpoint == "/v1/payments"
    assert notice.migration_endpoint == "/v2/payments"


def test_mark_deprecated_version_stored():
    dm = DeprecationManager()
    notice = dm.mark_deprecated("v1", "/v1/test", _future_date(), "/v2/test", "admin")
    assert notice.version == ApiVersion.V1


def test_mark_deprecated_unknown_version_raises():
    dm = DeprecationManager()
    with pytest.raises(ValueError, match="Unknown version"):
        dm.mark_deprecated("v99", "/v99/test", _future_date(), "/v2/test", "admin")


def test_check_approaching_sunset_within_threshold():
    dm = DeprecationManager()
    dm.mark_deprecated("v1", "/v1/test", _future_date(20), "/v2/test", "admin")
    upcoming = dm.check_approaching_sunset(days_threshold=30)
    assert len(upcoming) == 1


def test_check_approaching_sunset_outside_threshold():
    dm = DeprecationManager()
    dm.mark_deprecated("v1", "/v1/test", _future_date(60), "/v2/test", "admin")
    upcoming = dm.check_approaching_sunset(days_threshold=30)
    assert len(upcoming) == 0


def test_check_approaching_sunset_past_date_excluded():
    dm = DeprecationManager()
    dm.mark_deprecated("v1", "/v1/test", _past_date(), "/v2/test", "admin")
    upcoming = dm.check_approaching_sunset(days_threshold=30)
    # Past dates are days < 0, not in 0..30 range
    assert len(upcoming) == 0


def test_get_all_deprecations():
    dm = DeprecationManager()
    dm.mark_deprecated("v1", "/v1/a", _future_date(), "/v2/a", "admin")
    dm.mark_deprecated("v1", "/v1/b", _future_date(), "/v2/b", "admin")
    all_notices = dm.get_all_deprecations()
    assert len(all_notices) == 2


def test_generate_fca_notice_format():
    dm = DeprecationManager()
    dm.mark_deprecated("v1", "/v1/test", _future_date(), "/v2/test", "admin")
    fca = dm.generate_fca_notice("v1", "/v1/test")
    assert fca["regulatory_ref"] == "FCA COND 2.2"
    assert "psd2_ref" in fca
    assert "rfc" in fca
    assert fca["notice_period_days"] == 90


def test_generate_fca_notice_missing_raises():
    dm = DeprecationManager()
    with pytest.raises(ValueError):
        dm.generate_fca_notice("v1", "/v1/missing")


def test_calculate_days_until_sunset():
    dm = DeprecationManager()
    notice = dm.mark_deprecated("v1", "/v1/test", _future_date(45), "/v2/test", "admin")
    days = dm.calculate_days_until_sunset(notice.notice_id)
    assert days is not None
    assert 44 <= days <= 46  # allow ±1 day tolerance


def test_calculate_days_until_sunset_missing():
    dm = DeprecationManager()
    assert dm.calculate_days_until_sunset("dep_missing") is None


def test_trigger_sunset_notification_returns_hitl():
    dm = DeprecationManager()
    notice = dm.mark_deprecated("v1", "/v1/test", _future_date(), "/v2/test", "admin")
    proposal = dm.trigger_sunset_notification(notice.notice_id)
    assert isinstance(proposal, HITLProposal)
    assert proposal.requires_approval_from == "API_GOVERNANCE"


def test_trigger_sunset_notification_missing_raises():
    dm = DeprecationManager()
    with pytest.raises(ValueError):
        dm.trigger_sunset_notification("dep_missing")


def test_list_by_version():
    dm = DeprecationManager()
    dm.mark_deprecated("v1", "/v1/a", _future_date(), "/v2/a", "admin")
    dm.mark_deprecated("v2", "/v2/b", _future_date(), "/v3/b", "admin")
    v1_notices = dm.list_by_version("v1")
    assert len(v1_notices) == 1
    assert v1_notices[0].endpoint == "/v1/a"


def test_deprecation_created_at_is_set():
    dm = DeprecationManager()
    notice = dm.mark_deprecated("v1", "/v1/test", _future_date(), "/v2/test", "admin")
    assert notice.created_at is not None
    assert "T" in notice.created_at  # ISO format
