"""Unit tests for ADR-030 Step 1: RateLimiterPort + RedisRateLimiterAdapter.

Gap refs: G-API-01 (no rate limiting on auth) | G-API-02 (rate-limit coverage tests)
"""

from __future__ import annotations

import time
from unittest.mock import patch

from services.auth.redis_rate_limiter import RedisRateLimiterAdapter


def test_first_attempt_allowed() -> None:
    """First request within window is always allowed."""
    limiter = RedisRateLimiterAdapter(max_attempts=5, window_seconds=60, lockout_seconds=300)
    limiter.record_attempt("user-1", "/auth/login")
    result = limiter.check_rate("user-1", "/auth/login")

    assert result.allowed is True
    assert result.remaining == 4
    assert result.retry_after is None
    assert result.client_id == "user-1"
    assert result.endpoint == "/auth/login"


def test_rate_limit_exceeded() -> None:
    """After max_attempts, further requests are denied."""
    limiter = RedisRateLimiterAdapter(max_attempts=3, window_seconds=60, lockout_seconds=300)

    for _ in range(3):
        limiter.record_attempt("user-2", "/auth/login")

    result = limiter.check_rate("user-2", "/auth/login")

    assert result.allowed is False
    assert result.remaining == 0
    assert result.retry_after is not None
    assert result.retry_after > 0


def test_window_reset() -> None:
    """After window_seconds, attempts are no longer counted."""
    limiter = RedisRateLimiterAdapter(max_attempts=3, window_seconds=60, lockout_seconds=300)

    base_time = time.time()

    # Record 3 attempts "in the past" (beyond window)
    with patch("services.auth.redis_rate_limiter.time.time", return_value=base_time - 120):
        for _ in range(3):
            limiter.record_attempt("user-3", "/auth/login")

    # Now (current time) — window should be clear
    with patch("services.auth.redis_rate_limiter.time.time", return_value=base_time):
        result = limiter.check_rate("user-3", "/auth/login")

    assert result.allowed is True
    assert result.remaining == 3


def test_lockout_after_exceeded() -> None:
    """After exceeding limit, client enters lockout for lockout_seconds."""
    limiter = RedisRateLimiterAdapter(max_attempts=2, window_seconds=60, lockout_seconds=120)

    for _ in range(2):
        limiter.record_attempt("user-4", "/auth/sca/verify")

    # Trigger lockout
    result = limiter.check_rate("user-4", "/auth/sca/verify")
    assert result.allowed is False
    assert result.retry_after == 120

    # Subsequent check still locked
    result2 = limiter.check_rate("user-4", "/auth/sca/verify")
    assert result2.allowed is False
    assert result2.retry_after is not None


def test_different_endpoints_separate_limits() -> None:
    """Rate limits are tracked per endpoint, not globally."""
    limiter = RedisRateLimiterAdapter(max_attempts=2, window_seconds=60, lockout_seconds=300)

    # Exhaust /auth/login limit
    for _ in range(2):
        limiter.record_attempt("user-5", "/auth/login")

    login_result = limiter.check_rate("user-5", "/auth/login")
    assert login_result.allowed is False

    # /auth/refresh should still be allowed (separate limit)
    refresh_result = limiter.check_rate("user-5", "/auth/refresh")
    assert refresh_result.allowed is True
    assert refresh_result.remaining == 2


def test_stats_returns_correct_counts() -> None:
    """get_stats reflects current state across endpoints."""
    limiter = RedisRateLimiterAdapter(max_attempts=10, window_seconds=60, lockout_seconds=300)

    limiter.record_attempt("user-6", "/auth/login")
    limiter.record_attempt("user-6", "/auth/login")
    limiter.record_attempt("user-6", "/auth/refresh")

    stats = limiter.get_stats("user-6")

    assert stats.client_id == "user-6"
    assert stats.total_attempts == 3
    assert stats.window_attempts == 3
    assert stats.is_locked is False
    assert stats.lockout_expires is None
