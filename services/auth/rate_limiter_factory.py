"""Rate limiter DI factory (ADR-030, G-API-01/02).

Reads configuration from environment and returns a configured
RedisRateLimiterAdapter. Feature flag RATE_LIMIT_ENABLED controls activation.

Usage:
    from services.auth.rate_limiter_factory import get_rate_limiter
    limiter = get_rate_limiter()  # returns adapter or None if disabled
"""

from __future__ import annotations

import os

from services.auth.redis_rate_limiter import RedisRateLimiterAdapter


def get_rate_limiter() -> RedisRateLimiterAdapter | None:
    """Create rate limiter from env. Returns None if RATE_LIMIT_ENABLED != true."""
    enabled = os.environ.get("RATE_LIMIT_ENABLED", "true").lower() == "true"
    if not enabled:
        return None

    return RedisRateLimiterAdapter(
        max_attempts=int(os.environ.get("RATE_LIMIT_MAX_ATTEMPTS", "10")),
        window_seconds=int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60")),
        lockout_seconds=int(os.environ.get("RATE_LIMIT_LOCKOUT_SECONDS", "300")),
    )
