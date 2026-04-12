"""
services/transaction_monitor/scoring/velocity_tracker.py — Velocity Tracker
IL-RTM-01 | banxe-emi-stack

Redis-based sliding window velocity counters for AML monitoring.
Protocol DI: InMemoryVelocityTracker for tests, RedisVelocityTracker for production.

Invariants:
  I-02: Hard-block jurisdictions RU/BY/IR/KP/CU/MM/AF/VE enforced
  I-04: EDD threshold at GBP 10,000 cumulative (individual)
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Protocol, runtime_checkable

from services.transaction_monitor.config import get_config
from services.transaction_monitor.models.transaction import TransactionEvent

logger = logging.getLogger("banxe.transaction_monitor.velocity")

# Velocity window definitions (key suffix → seconds)
_WINDOWS = {
    "1h": 3600,
    "24h": 86400,
    "7d": 604800,
}


@runtime_checkable
class VelocityTrackerPort(Protocol):
    """Interface for velocity tracking."""

    def record(self, event: TransactionEvent) -> None: ...
    def get_count(self, customer_id: str, window: str) -> int: ...
    def get_cumulative_amount(self, customer_id: str, window: str) -> Decimal: ...
    def is_hard_blocked(self, event: TransactionEvent) -> bool: ...
    def requires_edd(self, customer_id: str) -> bool: ...


class InMemoryVelocityTracker:
    """Test stub — in-memory velocity tracker with configurable counts."""

    def __init__(self, counts: dict[str, int] | None = None) -> None:
        # counts: {"{customer_id}:{window}": count}
        self._counts: dict[str, int] = counts or {}
        self._amounts: dict[str, Decimal] = {}
        self._config = get_config()

    def record(self, event: TransactionEvent) -> None:
        """Record a transaction event into all windows."""
        for window in _WINDOWS:
            key = f"{event.sender_id}:{window}"
            self._counts[key] = self._counts.get(key, 0) + 1
            self._amounts[key] = self._amounts.get(key, Decimal("0")) + event.amount

    def get_count(self, customer_id: str, window: str) -> int:
        return self._counts.get(f"{customer_id}:{window}", 0)

    def get_cumulative_amount(self, customer_id: str, window: str) -> Decimal:
        return self._amounts.get(f"{customer_id}:{window}", Decimal("0"))

    def is_hard_blocked(self, event: TransactionEvent) -> bool:
        """I-02: block transactions from/to sanctioned jurisdictions."""
        jurisdictions = {event.sender_jurisdiction}
        if event.receiver_jurisdiction:
            jurisdictions.add(event.receiver_jurisdiction)
        return bool(jurisdictions & self._config.blocked_jurisdictions)

    def requires_edd(self, customer_id: str) -> bool:
        """I-04: EDD if cumulative 24h amount exceeds threshold."""
        amount_24h = self.get_cumulative_amount(customer_id, "24h")
        return amount_24h >= self._config.edd_threshold_individual_gbp


class RedisVelocityTracker:
    """Production Redis-backed velocity tracker using sorted sets.

    Uses ZADD with timestamps for sliding window counts.
    Deferred import: only imports redis when instantiated.
    """

    def __init__(self, redis_url: str | None = None) -> None:
        import redis as redis_lib

        url = redis_url or get_config().redis_url
        self._redis = redis_lib.from_url(url, decode_responses=True)
        self._config = get_config()

    def record(self, event: TransactionEvent) -> None:
        import time

        now = time.time()
        for window, ttl in _WINDOWS.items():
            count_key = f"vel:count:{event.sender_id}:{window}"
            amount_key = f"vel:amount:{event.sender_id}:{window}"
            pipe = self._redis.pipeline()
            pipe.zadd(count_key, {f"{event.transaction_id}:{now}": now})
            pipe.zremrangebyscore(count_key, 0, now - ttl)
            pipe.expire(count_key, ttl * 2)
            pipe.incrbyfloat(
                amount_key, float(event.amount)
            )  # nosemgrep: banxe-float-money — Redis incrbyfloat for velocity sum, not monetary calc
            pipe.expire(amount_key, ttl * 2)
            pipe.execute()

    def get_count(self, customer_id: str, window: str) -> int:
        import time

        ttl = _WINDOWS.get(window, 86400)
        now = time.time()
        key = f"vel:count:{customer_id}:{window}"
        return int(self._redis.zcount(key, now - ttl, now))

    def get_cumulative_amount(self, customer_id: str, window: str) -> Decimal:
        key = f"vel:amount:{customer_id}:{window}"
        val = self._redis.get(key)
        return Decimal(str(val)) if val else Decimal("0")

    def is_hard_blocked(self, event: TransactionEvent) -> bool:
        jurisdictions = {event.sender_jurisdiction}
        if event.receiver_jurisdiction:
            jurisdictions.add(event.receiver_jurisdiction)
        return bool(jurisdictions & self._config.blocked_jurisdictions)

    def requires_edd(self, customer_id: str) -> bool:
        amount_24h = self.get_cumulative_amount(customer_id, "24h")
        return amount_24h >= self._config.edd_threshold_individual_gbp
