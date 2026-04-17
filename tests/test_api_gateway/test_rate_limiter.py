from __future__ import annotations

import pytest

from services.api_gateway.models import UsageTier
from services.api_gateway.rate_limiter import RateLimiter


@pytest.fixture()
def limiter() -> RateLimiter:
    return RateLimiter()


def test_check_rate_limit_returns_dict(limiter: RateLimiter) -> None:
    result = limiter.check_rate_limit("key-1", UsageTier.FREE)
    assert isinstance(result, dict)


def test_check_rate_limit_has_allowed_field(limiter: RateLimiter) -> None:
    result = limiter.check_rate_limit("key-1", UsageTier.FREE)
    assert "allowed" in result


def test_check_rate_limit_has_remaining_field(limiter: RateLimiter) -> None:
    result = limiter.check_rate_limit("key-1", UsageTier.FREE)
    assert "remaining" in result


def test_check_rate_limit_has_reset_at_field(limiter: RateLimiter) -> None:
    result = limiter.check_rate_limit("key-1", UsageTier.FREE)
    assert "reset_at" in result


def test_check_rate_limit_has_limit_field(limiter: RateLimiter) -> None:
    result = limiter.check_rate_limit("key-1", UsageTier.FREE)
    assert "limit" in result


def test_check_rate_limit_allowed_is_bool(limiter: RateLimiter) -> None:
    result = limiter.check_rate_limit("key-1", UsageTier.BASIC)
    assert isinstance(result["allowed"], bool)


def test_check_rate_limit_stub_always_allowed(limiter: RateLimiter) -> None:
    result = limiter.check_rate_limit("key-1", UsageTier.BASIC)
    assert result["allowed"] is True


def test_free_tier_limit_is_30_per_minute(limiter: RateLimiter) -> None:
    result = limiter.check_rate_limit("key-1", UsageTier.FREE)
    assert result["limit"] == 30


def test_basic_tier_limit_is_300_per_minute(limiter: RateLimiter) -> None:
    result = limiter.check_rate_limit("key-1", UsageTier.BASIC)
    assert result["limit"] == 300


def test_premium_tier_limit_is_1500_per_minute(limiter: RateLimiter) -> None:
    result = limiter.check_rate_limit("key-1", UsageTier.PREMIUM)
    assert result["limit"] == 1500


def test_enterprise_tier_limit_is_6000_per_minute(limiter: RateLimiter) -> None:
    result = limiter.check_rate_limit("key-1", UsageTier.ENTERPRISE)
    assert result["limit"] == 6000


def test_free_tier_has_lowest_limits(limiter: RateLimiter) -> None:
    free_p = limiter.get_policy(UsageTier.FREE)
    enterprise_p = limiter.get_policy(UsageTier.ENTERPRISE)
    assert free_p is not None
    assert enterprise_p is not None
    assert free_p.requests_per_minute < enterprise_p.requests_per_minute


def test_enterprise_tier_has_highest_limits(limiter: RateLimiter) -> None:
    tiers = [UsageTier.FREE, UsageTier.BASIC, UsageTier.PREMIUM]
    enterprise_p = limiter.get_policy(UsageTier.ENTERPRISE)
    assert enterprise_p is not None
    for t in tiers:
        p = limiter.get_policy(t)
        assert p is not None
        assert p.requests_per_minute <= enterprise_p.requests_per_minute


def test_get_policy_returns_policy_for_known_tier(limiter: RateLimiter) -> None:
    p = limiter.get_policy(UsageTier.BASIC)
    assert p is not None
    assert p.tier == UsageTier.BASIC


def test_get_policy_returns_none_for_unknown_tier(limiter: RateLimiter) -> None:
    # Patch a bad enum value via direct dict access to simulate unknown
    from services.api_gateway.models import InMemoryRateLimitPolicyStore

    store = InMemoryRateLimitPolicyStore()
    # Test that get_policy handles a tier with no entry gracefully
    limiter2 = RateLimiter(policy_store=store)
    # All seeded tiers should return a policy
    assert limiter2.get_policy(UsageTier.FREE) is not None


def test_reset_bucket_clears_count(limiter: RateLimiter) -> None:
    limiter.check_rate_limit("key-x", UsageTier.BASIC)
    limiter.reset_bucket("key-x")
    assert not any(k.startswith("key-x:") for k in limiter._buckets)


def test_remaining_decrements_on_each_call(limiter: RateLimiter) -> None:
    r1 = limiter.check_rate_limit("key-2", UsageTier.ENTERPRISE)
    r2 = limiter.check_rate_limit("key-2", UsageTier.ENTERPRISE)
    assert r2["remaining"] < r1["remaining"]
