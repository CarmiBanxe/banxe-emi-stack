"""
tests/test_redis_velocity_tracker.py — RedisVelocityTracker tests
IL-048 | S9-04 | banxe-emi-stack

Uses fakeredis — a Redis-compatible in-memory server.
No real Redis required. fakeredis supports ZADD, ZRANGEBYSCORE, EXPIRE, PING.

Coverage:
  - Unit tests: record/query, window isolation, multi-customer, precision
  - Integration: RedisVelocityTracker → TxMonitorService (daily breach,
    monthly breach, structuring detection)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import fakeredis
import pytest

from services.aml.redis_velocity_tracker import (
    RedisVelocityTracker,
    RedisVelocityTrackerError,
)
from services.aml.tx_monitor import TxMonitorRequest, TxMonitorService


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def redis_client():
    """Isolated in-memory Redis per test (fakeredis)."""
    return fakeredis.FakeRedis()


@pytest.fixture
def tracker(redis_client):
    return RedisVelocityTracker(redis_client)


# ── 1. Basic record + get_daily ───────────────────────────────────────────────

def test_record_and_get_daily(tracker):
    tracker.record("cust-001", Decimal("500.00"))
    total, count = tracker.get_daily("cust-001")
    assert total == Decimal("500.00")
    assert count == 1


def test_get_daily_empty(tracker):
    total, count = tracker.get_daily("cust-unknown")
    assert total == Decimal("0")
    assert count == 0


def test_multiple_records_accumulate_daily(tracker):
    tracker.record("cust-001", Decimal("1000.00"))
    tracker.record("cust-001", Decimal("2500.50"))
    tracker.record("cust-001", Decimal("750.25"))
    total, count = tracker.get_daily("cust-001")
    assert total == Decimal("4250.75")
    assert count == 3


# ── 2. Time-window exclusion ──────────────────────────────────────────────────

def test_get_daily_excludes_old_records(redis_client):
    """Records older than 24 hours must not appear in get_daily()."""
    tracker = RedisVelocityTracker(redis_client)
    customer_id = "cust-002"
    key = f"banxe:velocity:{customer_id}"

    # Manually insert an old record (25 hours ago) directly into the sorted set
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).timestamp()
    redis_client.zadd(key, {f"old-uuid:{Decimal('9000')}": old_ts})

    # Record a recent transaction
    tracker.record(customer_id, Decimal("100.00"))

    total, count = tracker.get_daily(customer_id)
    # Only the recent record should appear
    assert count == 1
    assert total == Decimal("100.00")


def test_get_monthly_includes_recent_29_days(redis_client):
    """Records within 30 days appear in get_monthly()."""
    tracker = RedisVelocityTracker(redis_client)
    customer_id = "cust-003"
    key = f"banxe:velocity:{customer_id}"

    # 29 days ago — within monthly window
    ts_29d = (datetime.now(timezone.utc) - timedelta(days=29)).timestamp()
    redis_client.zadd(key, {f"old-uuid:{Decimal('5000')}": ts_29d})
    tracker.record(customer_id, Decimal("1000.00"))

    total, count = tracker.get_monthly(customer_id)
    assert count == 2
    assert total == Decimal("6000.00")


def test_get_monthly_excludes_31_day_old(redis_client):
    """Records older than 30 days must not appear in get_monthly()."""
    tracker = RedisVelocityTracker(redis_client)
    customer_id = "cust-004"
    key = f"banxe:velocity:{customer_id}"

    old_ts = (datetime.now(timezone.utc) - timedelta(days=31)).timestamp()
    redis_client.zadd(key, {f"old-uuid:{Decimal('50000')}": old_ts})

    tracker.record(customer_id, Decimal("200.00"))
    total, count = tracker.get_monthly(customer_id)
    assert count == 1
    assert total == Decimal("200.00")


def test_get_recent_window_custom_hours(tracker):
    """get_recent_window(hours=12) respects the custom window."""
    tracker.record("cust-005", Decimal("300.00"))
    tracker.record("cust-005", Decimal("300.00"))
    total, count = tracker.get_recent_window("cust-005", hours=12)
    assert count == 2
    assert total == Decimal("600.00")


# ── 3. Multi-customer isolation ───────────────────────────────────────────────

def test_multiple_customers_are_isolated(tracker):
    tracker.record("cust-A", Decimal("10000.00"))
    tracker.record("cust-B", Decimal("500.00"))

    total_a, count_a = tracker.get_daily("cust-A")
    total_b, count_b = tracker.get_daily("cust-B")

    assert total_a == Decimal("10000.00") and count_a == 1
    assert total_b == Decimal("500.00") and count_b == 1


# ── 4. Decimal precision ──────────────────────────────────────────────────────

def test_large_amount_decimal_precision(tracker):
    """£99,999.99 round-trips correctly through Redis member string."""
    amount = Decimal("99999.99")
    tracker.record("cust-006", amount)
    total, _ = tracker.get_daily("cust-006")
    assert total == amount


def test_zero_amount(tracker):
    tracker.record("cust-007", Decimal("0.00"))
    total, count = tracker.get_daily("cust-007")
    assert total == Decimal("0.00")
    assert count == 1


def test_high_precision_amounts_sum(tracker):
    """Multiple precise amounts accumulate without float drift."""
    tracker.record("cust-008", Decimal("1234.56"))
    tracker.record("cust-008", Decimal("7890.44"))
    total, _ = tracker.get_daily("cust-008")
    assert total == Decimal("9125.00")


# ── 5. Custom key prefix ──────────────────────────────────────────────────────

def test_custom_key_prefix(redis_client):
    tracker = RedisVelocityTracker(redis_client, key_prefix="test:vel")
    tracker.record("cust-prefix", Decimal("100.00"))

    # Key should use custom prefix
    assert redis_client.exists("test:vel:cust-prefix")
    assert not redis_client.exists("banxe:velocity:cust-prefix")


# ── 6. TTL and reset ──────────────────────────────────────────────────────────

def test_ttl_set_after_record(redis_client):
    tracker = RedisVelocityTracker(redis_client, ttl_seconds=86400)
    tracker.record("cust-ttl", Decimal("100.00"))
    ttl = redis_client.ttl("banxe:velocity:cust-ttl")
    # TTL should be set (positive, ≤ 86400)
    assert 0 < ttl <= 86400


def test_reset_clears_records(tracker):
    tracker.record("cust-reset", Decimal("500.00"))
    tracker.reset("cust-reset")
    total, count = tracker.get_daily("cust-reset")
    assert total == Decimal("0")
    assert count == 0


def test_reset_nonexistent_customer_is_noop(tracker):
    """Resetting a customer with no records should not raise."""
    tracker.reset("cust-ghost")  # Must not raise


# ── 7. Health check ───────────────────────────────────────────────────────────

def test_health_returns_true_when_redis_up(tracker):
    assert tracker.health() is True


def test_health_returns_false_when_redis_down():
    dead_redis = MagicMock()
    dead_redis.ping.side_effect = Exception("Connection refused")
    tracker = RedisVelocityTracker(dead_redis)
    assert tracker.health() is False


# ── 8. Error propagation ──────────────────────────────────────────────────────

def test_record_raises_on_redis_failure():
    bad_redis = MagicMock()
    bad_redis.pipeline.side_effect = Exception("Redis down")
    tracker = RedisVelocityTracker(bad_redis)
    with pytest.raises(RedisVelocityTrackerError, match="Failed to record"):
        tracker.record("cust-fail", Decimal("100.00"))


def test_query_raises_on_redis_failure():
    bad_redis = MagicMock()
    bad_redis.zrangebyscore.side_effect = Exception("Redis down")
    tracker = RedisVelocityTracker(bad_redis)
    with pytest.raises(RedisVelocityTrackerError, match="Failed to query"):
        tracker.get_daily("cust-fail")


# ── 9. Integration with TxMonitorService ─────────────────────────────────────

def test_integrates_tx_monitor_daily_breach(redis_client):
    """
    INDIVIDUAL: daily limit = £25,000 / 10 txs.
    Record £24,000 via tracker, then evaluate £2,000 → daily breach.
    """
    tracker = RedisVelocityTracker(redis_client)
    monitor = TxMonitorService(velocity_tracker=tracker)

    # Pre-load 24k of daily volume via tracker
    for _ in range(3):
        tracker.record("cust-daily", Decimal("8000.00"))

    result = monitor.evaluate(TxMonitorRequest(
        transaction_id="tx-daily-001",
        customer_id="cust-daily",
        entity_type="INDIVIDUAL",
        amount=Decimal("2000.00"),
        currency="GBP",
    ))
    assert result.velocity_daily_breach is True


def test_integrates_tx_monitor_monthly_breach(redis_client):
    """
    INDIVIDUAL: monthly limit = £100,000.
    Record £98,000 via tracker, then evaluate £3,000 → monthly breach.
    """
    tracker = RedisVelocityTracker(redis_client)
    monitor = TxMonitorService(velocity_tracker=tracker)

    for _ in range(98):
        tracker.record("cust-monthly", Decimal("1000.00"))

    result = monitor.evaluate(TxMonitorRequest(
        transaction_id="tx-monthly-001",
        customer_id="cust-monthly",
        entity_type="INDIVIDUAL",
        amount=Decimal("3000.00"),
        currency="GBP",
    ))
    assert result.velocity_monthly_breach is True


def test_integrates_tx_monitor_structuring(redis_client):
    """
    INDIVIDUAL: structuring = 3+ txs in 24h totalling ≥ £9,000,
    each individually below £10,000 EDD threshold.
    """
    tracker = RedisVelocityTracker(redis_client)
    monitor = TxMonitorService(velocity_tracker=tracker)

    # 2 previous sub-threshold txs (£3,000 each)
    tracker.record("cust-struct", Decimal("3000.00"))
    tracker.record("cust-struct", Decimal("3000.00"))

    # 3rd tx (£3,500) pushes count to 3 and total to £9,500 → structuring signal
    result = monitor.evaluate(TxMonitorRequest(
        transaction_id="tx-struct-003",
        customer_id="cust-struct",
        entity_type="INDIVIDUAL",
        amount=Decimal("3500.00"),
        currency="GBP",
    ))
    assert result.structuring_signal is True
