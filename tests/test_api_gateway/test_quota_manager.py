from __future__ import annotations

from datetime import UTC, datetime

import pytest

from services.api_gateway.models import (
    InMemoryQuotaStore,
    InMemoryRateLimitPolicyStore,
    UsageTier,
)
from services.api_gateway.quota_manager import QuotaManager, _day_window_end, _day_window_start


@pytest.fixture()
def manager() -> QuotaManager:
    return QuotaManager()


def test_check_quota_returns_dict(manager: QuotaManager) -> None:
    result = manager.check_quota("key-1", UsageTier.FREE)
    assert isinstance(result, dict)


def test_check_quota_has_allowed_field(manager: QuotaManager) -> None:
    result = manager.check_quota("key-1", UsageTier.FREE)
    assert "allowed" in result


def test_check_quota_has_used_field(manager: QuotaManager) -> None:
    result = manager.check_quota("key-1", UsageTier.FREE)
    assert "used" in result


def test_check_quota_has_limit_field(manager: QuotaManager) -> None:
    result = manager.check_quota("key-1", UsageTier.FREE)
    assert "limit" in result


def test_check_quota_has_reset_at_field(manager: QuotaManager) -> None:
    result = manager.check_quota("key-1", UsageTier.FREE)
    assert "reset_at" in result


def test_check_quota_initially_allowed(manager: QuotaManager) -> None:
    result = manager.check_quota("key-1", UsageTier.BASIC)
    assert result["allowed"] is True


def test_check_quota_used_starts_at_zero(manager: QuotaManager) -> None:
    result = manager.check_quota("key-new", UsageTier.FREE)
    assert result["used"] == 0


def test_increment_usage_creates_record(manager: QuotaManager) -> None:
    q = manager.increment_usage("key-1", UsageTier.FREE)
    assert q.request_count == 1
    assert q.key_id == "key-1"


def test_increment_usage_updates_count(manager: QuotaManager) -> None:
    manager.increment_usage("key-1", UsageTier.FREE)
    q2 = manager.increment_usage("key-1", UsageTier.FREE)
    assert q2.request_count == 2


def test_increment_usage_tier_stored(manager: QuotaManager) -> None:
    q = manager.increment_usage("key-1", UsageTier.PREMIUM)
    assert q.tier == UsageTier.PREMIUM


def test_check_quota_used_increments(manager: QuotaManager) -> None:
    manager.increment_usage("key-5", UsageTier.BASIC)
    manager.increment_usage("key-5", UsageTier.BASIC)
    result = manager.check_quota("key-5", UsageTier.BASIC)
    assert result["used"] == 2


def test_soft_limit_detection_80_percent() -> None:
    store = InMemoryQuotaStore()
    policy_store = InMemoryRateLimitPolicyStore()
    qm = QuotaManager(quota_store=store, policy_store=policy_store)

    policy = policy_store.get_policy(UsageTier.FREE)
    assert policy is not None
    daily_limit = policy.requests_per_hour * 24  # 500 * 24 = 12000
    soft_threshold = int(daily_limit * 0.8)  # 9600

    # Use direct increment to simulate near-soft-limit
    for _ in range(soft_threshold):
        qm.increment_usage("key-soft", UsageTier.FREE)

    result = qm.check_quota("key-soft", UsageTier.FREE)
    assert result["warning"] is True
    assert result["allowed"] is True


def test_hard_limit_blocks_at_100_percent() -> None:
    store = InMemoryQuotaStore()
    policy_store = InMemoryRateLimitPolicyStore()

    from datetime import UTC
    import uuid

    from services.api_gateway.models import RateLimitPolicy

    # Use a tiny limit to test hard block without 12000 iterations
    tiny_policy = RateLimitPolicy(
        policy_id=str(uuid.uuid4()),
        tier=UsageTier.FREE,
        requests_per_second=1,
        requests_per_minute=1,
        requests_per_hour=1,  # 1 * 24 = 24 daily limit
        burst_allowance=0,
        created_at=datetime.now(UTC),
    )
    policy_store.save(tiny_policy)
    qm = QuotaManager(quota_store=store, policy_store=policy_store)

    daily_limit = 1 * 24  # 24
    for _ in range(daily_limit):
        qm.increment_usage("key-hard", UsageTier.FREE)

    result = qm.check_quota("key-hard", UsageTier.FREE)
    assert result["allowed"] is False


def test_day_window_start_is_midnight_utc() -> None:
    now = datetime.now(UTC)
    ws = _day_window_start(now)
    assert ws.hour == 0
    assert ws.minute == 0
    assert ws.second == 0


def test_day_window_end_is_end_of_day_utc() -> None:
    now = datetime.now(UTC)
    we = _day_window_end(now)
    assert we.hour == 23
    assert we.minute == 59
    assert we.second == 59


def test_get_usage_summary_empty(manager: QuotaManager) -> None:
    result = manager.get_usage_summary("no-such-key")
    assert result["total_windows"] == 0
    assert result["records"] == []


def test_get_usage_summary_populated(manager: QuotaManager) -> None:
    manager.increment_usage("key-s", UsageTier.BASIC)
    result = manager.get_usage_summary("key-s")
    assert result["total_windows"] == 1
    assert len(result["records"]) == 1
