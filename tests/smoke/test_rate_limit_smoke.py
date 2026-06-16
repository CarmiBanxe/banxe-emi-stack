"""Smoke tests for ADR-030 Step 3: auth rate-limit CI verification.

Gap refs: G-API-01 (no rate limiting on auth) | G-API-02 (rate-limit coverage tests)

Verifies that rate-limit protection is wired and functional on canonical
auth endpoints without requiring external Redis or a running server.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from services.auth.rate_limiter_factory import get_rate_limiter
from services.auth.redis_rate_limiter import RedisRateLimiterAdapter


def test_rate_limiter_active_in_default_config() -> None:
    """Rate limiter is active by default (RATE_LIMIT_ENABLED defaults to true)."""
    env = {k: v for k, v in os.environ.items() if k != "RATE_LIMIT_ENABLED"}
    with patch.dict(os.environ, env, clear=True):
        limiter = get_rate_limiter()
    assert limiter is not None
    assert isinstance(limiter, RedisRateLimiterAdapter)


def test_repeated_attempts_hit_rate_limit() -> None:
    """Simulated login flood triggers rate-limit denial."""
    limiter = RedisRateLimiterAdapter(max_attempts=5, window_seconds=60, lockout_seconds=60)

    # Simulate 5 rapid login attempts from same IP
    for _ in range(5):
        limiter.record_attempt("flood-ip", "/auth/login")

    result = limiter.check_rate("flood-ip", "/auth/login")
    assert result.allowed is False
    assert result.retry_after is not None
    assert result.retry_after > 0


def test_limited_client_receives_correct_fields() -> None:
    """Rate-limited response includes expected fields for canonical API error."""
    limiter = RedisRateLimiterAdapter(max_attempts=2, window_seconds=60, lockout_seconds=120)

    for _ in range(2):
        limiter.record_attempt("abuser", "/auth/login")

    result = limiter.check_rate("abuser", "/auth/login")
    assert result.allowed is False
    assert result.remaining == 0
    assert result.retry_after == 120
    assert result.client_id == "abuser"
    assert result.endpoint == "/auth/login"


def test_below_threshold_request_succeeds() -> None:
    """Normal usage below threshold is always allowed."""
    limiter = RedisRateLimiterAdapter(max_attempts=10, window_seconds=60, lockout_seconds=300)

    limiter.record_attempt("good-user", "/auth/login")
    result = limiter.check_rate("good-user", "/auth/login")

    assert result.allowed is True
    assert result.remaining == 9
    assert result.retry_after is None


def test_router_wiring_check_rate_limit_exists() -> None:
    """Auth router has _check_rate_limit function wired (boot-level verification)."""
    import api.routers.auth as auth_mod

    assert hasattr(auth_mod, "_check_rate_limit"), "rate-limit check not wired in router"
    assert callable(auth_mod._check_rate_limit)
    # _rate_limiter should be populated (default RATE_LIMIT_ENABLED=true)
    assert hasattr(auth_mod, "_rate_limiter")
