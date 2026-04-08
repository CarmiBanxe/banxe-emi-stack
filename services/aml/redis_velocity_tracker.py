"""
services/aml/redis_velocity_tracker.py — Redis-backed VelocityTracker
IL-048 | S9-04 | banxe-emi-stack

Production implementation of VelocityTrackerPort using Redis Sorted Sets.
Replaces InMemoryVelocityTracker in live environments.

Why Redis sorted sets?
-----------------------
Each customer has ONE sorted set key: `banxe:velocity:{customer_id}`.
  - Score  = Unix timestamp (float) → enables O(log N) range queries by time
  - Member = `{uuid4}:{decimal_amount}` → unique per transaction, parseable
  - TTL    = 32 days on the key → auto-expires without a cleanup job

Time-window queries (daily / monthly / custom hours) use ZRANGEBYSCORE:
  min_score = (now - window_seconds).timestamp()
  max_score = now.timestamp()

Cluster safety:
  - All operations target a single key per customer → no cross-slot issues
  - ZADD + EXPIRE are pipelined (transaction=False) → compatible with Redis Cluster

FCA audit trail:
  - RedisVelocityTracker is READ/WRITE for velocity state only.
  - Authoritative audit records live in ClickHouse (handled by TxMonitorService caller).

Usage:
    import redis
    from services.aml.redis_velocity_tracker import RedisVelocityTracker
    from services.aml.tx_monitor import TxMonitorService

    r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=False)
    tracker = RedisVelocityTracker(r)
    monitor = TxMonitorService(velocity_tracker=tracker)

    # evaluate BEFORE payment
    result = monitor.evaluate(req)
    # record AFTER payment succeeds
    monitor.record(customer_id, amount)
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis as _redis

logger = logging.getLogger(__name__)

# TTL covers monthly window (30 days) + 2-day buffer for DST / clock skew
_DEFAULT_TTL_SECONDS = 32 * 24 * 3600  # 32 days


class RedisVelocityTrackerError(Exception):
    """Raised when Redis is unavailable or returns unexpected data."""


class RedisVelocityTracker:
    """
    Production VelocityTracker backed by Redis Sorted Sets.

    Implements VelocityTrackerPort (structural typing — no explicit inheritance
    required; duck-typed by TxMonitorService).

    Thread-safe: redis-py uses a connection pool; each operation is atomic.
    Cluster-safe: all ops target a single key → no cross-slot MULTI/EXEC needed.
    """

    def __init__(
        self,
        redis_client: "_redis.Redis",
        key_prefix: str = "banxe:velocity",
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> None:
        self._redis = redis_client
        self._prefix = key_prefix
        self._ttl = ttl_seconds

    # ── Public interface (VelocityTrackerPort) ────────────────────────────────

    def record(self, customer_id: str, amount: Decimal) -> None:
        """
        Record a completed transaction in the velocity window.
        Call AFTER payment succeeds, not before evaluate().

        Uses pipeline (ZADD + EXPIRE) — two commands, not transactional,
        but safe for cluster because they target the same key.
        """
        key = self._key(customer_id)
        now_ts = datetime.now(timezone.utc).timestamp()
        # Member is unique per record; rsplit(":", 1) on decode splits correctly
        # even if UUID contains "-" (hyphens only, no colons).
        member = f"{uuid.uuid4()}:{amount}"

        try:
            pipe = self._redis.pipeline(transaction=False)
            pipe.zadd(key, {member: now_ts})
            pipe.expire(key, self._ttl)
            pipe.execute()
        except Exception as exc:
            logger.error(
                "RedisVelocityTracker.record failed: customer=%s exc=%s",
                customer_id, exc,
            )
            raise RedisVelocityTrackerError(
                f"Failed to record velocity for {customer_id}: {exc}"
            ) from exc

    def get_daily(self, customer_id: str) -> tuple[Decimal, int]:
        """Return (total_amount, tx_count) for the past 24 hours."""
        since = datetime.now(timezone.utc) - timedelta(days=1)
        return self._query_window(customer_id, since)

    def get_monthly(self, customer_id: str) -> tuple[Decimal, int]:
        """Return (total_amount, tx_count) for the past 30 days."""
        since = datetime.now(timezone.utc) - timedelta(days=30)
        return self._query_window(customer_id, since)

    def get_recent_window(
        self, customer_id: str, hours: int
    ) -> tuple[Decimal, int]:
        """Return (total_amount, tx_count) for the past `hours` hours."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        return self._query_window(customer_id, since)

    # ── Extras (not in VelocityTrackerPort, available for ops/tests) ──────────

    def reset(self, customer_id: str) -> None:
        """Delete all velocity records for a customer. Test helper / GDPR erasure."""
        try:
            self._redis.delete(self._key(customer_id))
        except Exception as exc:
            raise RedisVelocityTrackerError(
                f"Failed to reset velocity for {customer_id}: {exc}"
            ) from exc

    def health(self) -> bool:
        """True if Redis responds to PING."""
        try:
            return self._redis.ping()
        except Exception:
            return False

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _key(self, customer_id: str) -> str:
        return f"{self._prefix}:{customer_id}"

    def _query_window(
        self, customer_id: str, since: datetime
    ) -> tuple[Decimal, int]:
        """
        Fetch all records in [since, now] from the sorted set.
        Returns (sum_of_amounts, count).
        """
        key = self._key(customer_id)
        now_ts = datetime.now(timezone.utc).timestamp()
        since_ts = since.timestamp()

        try:
            raw_members: list[bytes] = self._redis.zrangebyscore(
                key, since_ts, now_ts
            )
        except Exception as exc:
            logger.error(
                "RedisVelocityTracker.query failed: customer=%s exc=%s",
                customer_id, exc,
            )
            raise RedisVelocityTrackerError(
                f"Failed to query velocity for {customer_id}: {exc}"
            ) from exc

        total = Decimal("0")
        for raw in raw_members:
            member = raw.decode() if isinstance(raw, bytes) else raw
            # member format: "{uuid}:{amount}" — split from right, maxsplit=1
            # UUID has hyphens not colons, so rsplit(":", 1) is unambiguous.
            _, amount_str = member.rsplit(":", 1)
            total += Decimal(amount_str)

        return total, len(raw_members)
