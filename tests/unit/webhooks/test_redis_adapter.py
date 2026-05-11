"""
test_redis_adapter.py — RedisWebhookReliabilityAdapter tests (ADR-034 Step 4).

Uses the hand-rolled FakeRedis double from tests/unit/webhooks/_fakes.py
to keep tests deterministic without a real Redis instance or fakeredis dep.
"""

from __future__ import annotations

import json

from services.webhooks.redis_adapter import (
    DEDUP_KEY_PREFIX,
    DLQ_KEY,
    DUE_KEY,
    RECORD_KEY_PREFIX,
    RedisWebhookReliabilityAdapter,
)
from services.webhooks.reliability_port import WebhookDeliveryRecord
from tests.unit.webhooks._fakes import FakeRedis


def _build(
    start_time: float = 1000.0,
    backoff: tuple[float, ...] = (1.0, 10.0, 60.0),
    max_attempts: int = 3,
    dedup_ttl_s: int = 86400,
):
    clock = [start_time]
    fake = FakeRedis(clock=lambda: clock[0])
    captured: list[WebhookDeliveryRecord] = []

    def hook(record: WebhookDeliveryRecord) -> None:
        captured.append(record)

    adapter = RedisWebhookReliabilityAdapter(
        redis_client=fake,
        max_attempts=max_attempts,
        backoff_schedule=backoff,
        dlq_alert_hook=hook,
        dedup_ttl_s=dedup_ttl_s,
        clock=lambda: clock[0],
    )
    return adapter, fake, clock, captured


def test_enqueue_creates_record_and_adds_to_due() -> None:
    adapter, fake, _clock, _captured = _build(start_time=1000.0)
    adapter.enqueue("ev-1", {"k": "v"}, "https://x")
    h = fake.hgetall(RECORD_KEY_PREFIX + "ev-1")
    assert h["event_id"] == "ev-1"
    assert json.loads(h["payload"]) == {"k": "v"}
    assert h["target_url"] == "https://x"
    assert h["status"] == "pending"
    assert h["attempt"] == "0"
    assert h["next_retry_at"] == "1000.0"
    # Due zset has the event at score=1000
    assert fake._zsets[DUE_KEY] == {"ev-1": 1000.0}


def test_enqueue_setnx_dedup_skips_duplicate_event_id() -> None:
    adapter, fake, _clock, _captured = _build()
    adapter.enqueue("ev-1", {"a": 1}, "https://x")
    # Mutate via second enqueue with different payload — should be IGNORED.
    adapter.enqueue("ev-1", {"a": 999}, "https://x")
    h = fake.hgetall(RECORD_KEY_PREFIX + "ev-1")
    assert json.loads(h["payload"]) == {"a": 1}


def test_dedup_key_ttl_set_on_enqueue() -> None:
    adapter, fake, _clock, _captured = _build(dedup_ttl_s=3600)
    adapter.enqueue("ev-1", {}, "https://x")
    assert fake.exists(DEDUP_KEY_PREFIX + "ev-1") == 1
    assert fake.ttl(DEDUP_KEY_PREFIX + "ev-1") == 3600


def test_mark_delivered_removes_record_and_due_entry() -> None:
    adapter, fake, _clock, _captured = _build()
    adapter.enqueue("ev-1", {}, "https://x")
    adapter.mark_delivered("ev-1")
    assert fake.hgetall(RECORD_KEY_PREFIX + "ev-1") == {}
    assert fake._zsets.get(DUE_KEY, {}) == {}


def test_mark_failed_increments_attempt_and_reschedules_with_backoff() -> None:
    adapter, fake, clock, _captured = _build(start_time=1000.0)
    adapter.enqueue("ev-1", {}, "https://x")
    clock[0] = 1000.0
    adapter.mark_failed("ev-1", "upstream 500")
    h = fake.hgetall(RECORD_KEY_PREFIX + "ev-1")
    assert h["attempt"] == "1"
    assert h["status"] == "pending"
    assert float(h["next_retry_at"]) == 1001.0  # backoff[0] = 1.0
    assert h["last_error"] == "upstream 500"
    # Due zset rescheduled
    assert fake._zsets[DUE_KEY]["ev-1"] == 1001.0


def test_mark_failed_at_max_attempts_pushes_to_dlq_and_fires_alert() -> None:
    adapter, fake, clock, captured = _build(start_time=0.0, backoff=(1.0, 1.0), max_attempts=2)
    adapter.enqueue("ev-1", {"applicantId": "a1"}, "https://x")
    adapter.mark_failed("ev-1", "first")  # attempt=1, still pending
    assert fake._lists.get(DLQ_KEY) is None
    assert captured == []
    adapter.mark_failed("ev-1", "second")  # attempt=2 == max → dead

    # Record removed from active storage
    assert fake.hgetall(RECORD_KEY_PREFIX + "ev-1") == {}
    assert fake._zsets.get(DUE_KEY, {}).get("ev-1") is None

    # DLQ has snapshot
    dlq = fake.lrange(DLQ_KEY, 0, -1)
    assert len(dlq) == 1
    snap = json.loads(dlq[0])
    assert snap["event_id"] == "ev-1"
    assert snap["status"] == "dead"
    assert snap["attempt"] == 2
    assert snap["last_error"] == "second"
    assert snap["target_url"] == "https://x"
    assert snap["payload"] == {"applicantId": "a1"}

    # Alert hook fired exactly once with the dead-state record
    assert len(captured) == 1
    rec = captured[0]
    assert rec.event_id == "ev-1"
    assert rec.status == "dead"
    assert rec.attempt == 2
    assert rec.last_error == "second"


def test_next_due_returns_only_records_with_score_le_now() -> None:
    adapter, fake, clock, _captured = _build(start_time=100.0)
    adapter.enqueue("ev-a", {}, "https://x")  # score=100
    clock[0] = 100.0
    adapter.mark_failed("ev-a", "err")  # → next_retry_at=101
    # Add a fresh one due at t=100
    clock[0] = 100.0
    adapter.enqueue("ev-b", {}, "https://x")  # score=100

    # At t=100: only ev-b is due (ev-a is at 101)
    due_now = adapter.next_due(now_ts=100.0, limit=10)
    assert [r.event_id for r in due_now] == ["ev-b"]
    # At t=101: both due, ev-b first (score 100) then ev-a (score 101)
    due_later = adapter.next_due(now_ts=101.0, limit=10)
    assert [r.event_id for r in due_later] == ["ev-b", "ev-a"]


def test_next_due_respects_batch_limit_and_order() -> None:
    adapter, fake, clock, _captured = _build(start_time=100.0)
    # 5 records all due at t=100; FakeRedis sorts by (score, member),
    # so order ties break alphabetically.
    for i in range(5):
        adapter.enqueue(f"ev-{i}", {}, "https://x")
    capped = adapter.next_due(now_ts=100.0, limit=2)
    assert [r.event_id for r in capped] == ["ev-0", "ev-1"]
    full = adapter.next_due(now_ts=100.0, limit=10)
    assert [r.event_id for r in full] == [f"ev-{i}" for i in range(5)]


def test_dead_record_excluded_from_next_due() -> None:
    adapter, _fake, _clock, _captured = _build(start_time=0.0, backoff=(1.0,), max_attempts=1)
    adapter.enqueue("ev-1", {}, "https://x")
    adapter.mark_failed("ev-1", "exhausted immediately")  # attempt=1 == max → dead
    # No live record remains → next_due empty even at far-future now
    assert adapter.next_due(now_ts=10_000.0, limit=10) == []


def test_dlq_alert_hook_receives_canonical_record() -> None:
    adapter, _fake, _clock, captured = _build(start_time=0.0, backoff=(1.0,), max_attempts=1)
    adapter.enqueue("ev-1", {"hello": "world"}, "https://example/hook")
    adapter.mark_failed("ev-1", "boom")
    assert len(captured) == 1
    rec = captured[0]
    assert rec.event_id == "ev-1"
    assert rec.payload == {"hello": "world"}
    assert rec.target_url == "https://example/hook"
    assert rec.last_error == "boom"
    assert rec.status == "dead"


def test_alert_hook_exception_does_not_break_mark_failed() -> None:
    # If the alert sink raises, mark_failed must still complete; the record
    # must still be DLQ'd and removed from the active set.
    from tests.unit.webhooks._fakes import FakeRedis

    fake = FakeRedis()

    def broken_hook(_record: WebhookDeliveryRecord) -> None:
        raise RuntimeError("alert sink down")

    adapter = RedisWebhookReliabilityAdapter(
        redis_client=fake,
        max_attempts=1,
        backoff_schedule=(1.0,),
        dlq_alert_hook=broken_hook,
        dedup_ttl_s=60,
    )
    adapter.enqueue("ev-1", {}, "https://x")
    adapter.mark_failed("ev-1", "boom")
    assert fake.hgetall(RECORD_KEY_PREFIX + "ev-1") == {}
    assert len(fake.lrange(DLQ_KEY, 0, -1)) == 1
