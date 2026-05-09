"""RateLimiterPort — abstract rate limiting interface (ADR-030, G-API-01/02).

Defines the port for auth-surface rate limiting. Concrete adapters
(RedisRateLimiterAdapter) implement sliding-window rate limiting per endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class RateCheckResult:
    """Result of a rate-limit check."""

    allowed: bool
    remaining: int
    retry_after: int | None
    client_id: str
    endpoint: str


@dataclass(frozen=True)
class RateStats:
    """Rate limiting statistics for a client."""

    client_id: str
    total_attempts: int
    window_attempts: int
    is_locked: bool
    lockout_expires: datetime | None


class RateLimiterPort(Protocol):
    """Abstract port for auth-surface rate limiting (ADR-030)."""

    def check_rate(self, client_id: str, endpoint: str) -> RateCheckResult: ...

    def record_attempt(self, client_id: str, endpoint: str) -> None: ...

    def get_stats(self, client_id: str) -> RateStats: ...
