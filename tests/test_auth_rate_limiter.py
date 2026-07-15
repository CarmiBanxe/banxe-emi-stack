# tests/test_auth_rate_limiter.py
# Redis rate limiter — coverage gap closer (lines 56-57, 129-131)
# services/auth/redis_rate_limiter.py

from datetime import UTC
import time
from unittest.mock import patch

import pytest

from services.auth.redis_rate_limiter import RedisRateLimiterAdapter

CLIENT = "test-client"
ENDPOINT = "/auth/login"


@pytest.fixture
def limiter():
    return RedisRateLimiterAdapter(max_attempts=3, window_seconds=60, lockout_seconds=10)


def _enter_lockout(limiter):
    """Exhaust the limit so the next check_rate places the client in lockout."""
    for _ in range(3):
        limiter.record_attempt(CLIENT, ENDPOINT)
    result = limiter.check_rate(CLIENT, ENDPOINT)
    assert not result.allowed  # window_count >= max_attempts -> lockout


class TestLockoutExpiry:
    """Lines 56-57: an expired lockout is deleted and _is_locked returns (False, None)."""

    def test_lockout_expires_allows_again(self, limiter):
        _enter_lockout(limiter)
        # Advance past BOTH the lockout (10s) AND the sliding window (60s): only then
        # do the recorded attempts age out, so check_rate does not immediately re-lock.
        with patch("services.auth.redis_rate_limiter.time") as mock_time:
            mock_time.time.return_value = time.time() + 61
            result = limiter.check_rate(CLIENT, ENDPOINT)
        assert result.allowed  # lockout expired + window cleared -> allowed again

    def test_lockout_expiry_clears_lockout_entry(self, limiter):
        _enter_lockout(limiter)
        key = limiter._key(CLIENT, ENDPOINT)
        assert key in limiter._lockouts

        with patch("services.auth.redis_rate_limiter.time") as mock_time:
            mock_time.time.return_value = time.time() + 61
            limiter.check_rate(CLIENT, ENDPOINT)
        assert key not in limiter._lockouts  # expiry branch deleted it, no re-lock

    def test_check_rate_while_locked_returns_retry_after(self, limiter):
        """Active-lockout path: check_rate returns allowed=False + a positive retry_after."""
        _enter_lockout(limiter)  # lockout is now active (not yet expired)
        result = limiter.check_rate(CLIENT, ENDPOINT)
        assert not result.allowed
        assert result.retry_after is not None
        assert result.retry_after > 0


class TestGetStatsWhileLocked:
    """Lines 129-131: get_stats reports lockout state for a locked client."""

    def test_get_stats_is_locked_true(self, limiter):
        _enter_lockout(limiter)
        stats = limiter.get_stats(CLIENT)
        assert stats.is_locked is True

    def test_get_stats_lockout_expires_is_datetime_utc(self, limiter):
        _enter_lockout(limiter)
        stats = limiter.get_stats(CLIENT)
        assert stats.lockout_expires is not None
        assert stats.lockout_expires.tzinfo is UTC

    def test_get_stats_not_locked(self, limiter):
        limiter.record_attempt(CLIENT, ENDPOINT)
        stats = limiter.get_stats(CLIENT)
        assert stats.is_locked is False
        assert stats.lockout_expires is None
