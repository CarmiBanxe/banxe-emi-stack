"""RedisRateLimiterAdapter — sliding window rate limiter (ADR-030, G-API-01/02).

Uses an in-memory store (dict-based) for testing or a Redis-compatible backend
for production. Implements per-endpoint sliding window with lockout.

Environment variables:
    RATE_LIMIT_MAX_ATTEMPTS     Max attempts per window (default: 10)
    RATE_LIMIT_WINDOW_SECONDS   Sliding window duration (default: 60)
    RATE_LIMIT_LOCKOUT_SECONDS  Lockout duration after exceeding limit (default: 300)
"""

from __future__ import annotations

from datetime import UTC, datetime
import time

from services.auth.rate_limiter import RateCheckResult, RateStats


class RedisRateLimiterAdapter:
    """Sliding window rate limiter with per-endpoint tracking and lockout.

    Uses an in-memory dict for unit testing. Production wiring (Step 2) will
    inject a Redis client for multi-instance durability.
    """

    def __init__(
        self,
        *,
        max_attempts: int = 10,
        window_seconds: int = 60,
        lockout_seconds: int = 300,
        redis_client: object | None = None,
    ) -> None:
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._lockout_seconds = lockout_seconds
        self._redis = redis_client
        # In-memory fallback for testing (no Redis required)
        self._attempts: dict[str, list[float]] = {}
        self._lockouts: dict[str, float] = {}
        self._total_attempts: dict[str, int] = {}

    def _key(self, client_id: str, endpoint: str) -> str:
        return f"{client_id}:{endpoint}"

    def _now(self) -> float:
        return time.time()

    def _is_locked(self, key: str) -> tuple[bool, float | None]:
        """Check if key is in lockout. Returns (is_locked, expires_at)."""
        expires_at = self._lockouts.get(key)
        if expires_at is None:
            return False, None
        if self._now() >= expires_at:
            del self._lockouts[key]
            return False, None
        return True, expires_at

    def _window_count(self, key: str) -> int:
        """Count attempts within the current sliding window."""
        attempts = self._attempts.get(key, [])
        cutoff = self._now() - self._window_seconds
        valid = [t for t in attempts if t > cutoff]
        self._attempts[key] = valid
        return len(valid)

    def check_rate(self, client_id: str, endpoint: str) -> RateCheckResult:
        """Check whether the client is allowed to proceed."""
        key = self._key(client_id, endpoint)

        locked, expires_at = self._is_locked(key)
        if locked:
            retry_after = int(expires_at - self._now()) + 1 if expires_at else self._lockout_seconds
            return RateCheckResult(
                allowed=False,
                remaining=0,
                retry_after=retry_after,
                client_id=client_id,
                endpoint=endpoint,
            )

        window_count = self._window_count(key)
        remaining = max(0, self._max_attempts - window_count)

        if window_count >= self._max_attempts:
            # Enter lockout
            self._lockouts[key] = self._now() + self._lockout_seconds
            return RateCheckResult(
                allowed=False,
                remaining=0,
                retry_after=self._lockout_seconds,
                client_id=client_id,
                endpoint=endpoint,
            )

        return RateCheckResult(
            allowed=True,
            remaining=remaining,
            retry_after=None,
            client_id=client_id,
            endpoint=endpoint,
        )

    def record_attempt(self, client_id: str, endpoint: str) -> None:
        """Record an authentication attempt."""
        key = self._key(client_id, endpoint)
        if key not in self._attempts:
            self._attempts[key] = []
        self._attempts[key].append(self._now())

        if key not in self._total_attempts:
            self._total_attempts[key] = 0
        self._total_attempts[key] += 1

    def get_stats(self, client_id: str) -> RateStats:
        """Get rate limiting statistics for a client (across all endpoints)."""
        total = 0
        window = 0
        is_locked = False
        lockout_expires: datetime | None = None

        for key, count in self._total_attempts.items():
            if key.startswith(f"{client_id}:"):
                total += count
                window += self._window_count(key)
                locked, expires_at = self._is_locked(key)
                if locked:
                    is_locked = True
                    if expires_at:
                        lockout_expires = datetime.fromtimestamp(expires_at, tz=UTC)

        return RateStats(
            client_id=client_id,
            total_attempts=total,
            window_attempts=window,
            is_locked=is_locked,
            lockout_expires=lockout_expires,
        )
