"""Integration tests for ADR-030 Step 2: rate-limit wiring into auth flow.

Gap refs: G-API-01 (no rate limiting on auth) | G-API-02 (rate-limit coverage tests)
"""

from __future__ import annotations

import os
from unittest.mock import patch

from services.auth.rate_limiter_factory import get_rate_limiter
from services.auth.redis_rate_limiter import RedisRateLimiterAdapter


def test_factory_returns_adapter_when_enabled() -> None:
    """RATE_LIMIT_ENABLED=true returns configured adapter."""
    env = {
        "RATE_LIMIT_ENABLED": "true",
        "RATE_LIMIT_MAX_ATTEMPTS": "5",
        "RATE_LIMIT_WINDOW_SECONDS": "30",
        "RATE_LIMIT_LOCKOUT_SECONDS": "120",
    }
    with patch.dict(os.environ, env, clear=False):
        limiter = get_rate_limiter()

    assert isinstance(limiter, RedisRateLimiterAdapter)
    assert limiter._max_attempts == 5
    assert limiter._window_seconds == 30
    assert limiter._lockout_seconds == 120


def test_factory_returns_none_when_disabled() -> None:
    """RATE_LIMIT_ENABLED=false returns None (no-op)."""
    env = {"RATE_LIMIT_ENABLED": "false"}
    with patch.dict(os.environ, env, clear=False):
        limiter = get_rate_limiter()

    assert limiter is None


def test_login_allowed_under_threshold() -> None:
    """Login attempts under max_attempts are all allowed."""
    limiter = RedisRateLimiterAdapter(max_attempts=5, window_seconds=60, lockout_seconds=300)

    for i in range(5):
        limiter.record_attempt("192.168.1.1", "/auth/login")
        if i < 4:
            result = limiter.check_rate("192.168.1.1", "/auth/login")
            assert result.allowed is True, f"Attempt {i + 1} should be allowed"


def test_login_blocked_after_threshold() -> None:
    """Login blocked with retry_after after exceeding max_attempts."""
    limiter = RedisRateLimiterAdapter(max_attempts=3, window_seconds=60, lockout_seconds=120)

    for _ in range(3):
        limiter.record_attempt("10.0.0.1", "/auth/login")

    result = limiter.check_rate("10.0.0.1", "/auth/login")
    assert result.allowed is False
    assert result.retry_after == 120
    assert result.remaining == 0
    assert result.endpoint == "/auth/login"


def test_separate_endpoints_independent() -> None:
    """Rate limits on /auth/login do not affect /auth/token/refresh."""
    limiter = RedisRateLimiterAdapter(max_attempts=2, window_seconds=60, lockout_seconds=300)

    # Exhaust login limit
    for _ in range(2):
        limiter.record_attempt("client-x", "/auth/login")

    login_check = limiter.check_rate("client-x", "/auth/login")
    assert login_check.allowed is False

    # Refresh endpoint still open
    refresh_check = limiter.check_rate("client-x", "/auth/token/refresh")
    assert refresh_check.allowed is True


def test_rate_limit_wiring_in_router_module() -> None:
    """Verify the auth router imports rate-limit machinery."""
    import api.routers.auth as auth_module

    assert hasattr(auth_module, "_check_rate_limit")
    assert hasattr(auth_module, "_rate_limiter")
