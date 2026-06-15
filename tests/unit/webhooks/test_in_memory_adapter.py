"""
test_in_memory_adapter.py — Unit tests for InMemoryWebhookAdapter (ADR-034 Step 1).

All tests are deterministic: clock is injected as a closure over a mutable list
so we can advance "now" explicitly without time.sleep.
"""

from __future__ import annotations

from services.webhooks.in_memory_adapter import (
    DEFAULT_BACKOFF_SCHEDULE,
    DEFAULT_MAX_ATTEMPTS,
    InMemoryWebhookAdapter,
)


def _make_adapter(
    start_time: float = 1000.0,
    backoff: tuple[float, ...] = DEFAULT_BACKOFF_SCHEDULE,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> tuple[InMemoryWebhookAdapter, list[float]]:
    """Build an adapter with a mutable clock list; tests mutate `clock[0]`."""
    clock = [start_time]
    adapter = InMemoryWebhookAdapter(
        backoff_schedule=backoff,
        max_attempts=max_attempts,
        clock=lambda: clock[0],
    )
    return adapter, clock


def test_enqueue_creates_pending_record() -> None:
    adapter, clock = _make_adapter(start_time=1000.0)
    adapter.enqueue(
        event_id="ev-1",
        payload={"applicantId": "a1", "type": "applicantReviewed"},
        target_url="https://kc.internal/webhooks/sumsub",
    )
    due = adapter.next_due(now_ts=1000.0, limit=10)
    assert len(due) == 1
    r = due[0]
    assert r.event_id == "ev-1"
    assert r.status == "pending"
    assert r.attempt == 0
    assert r.next_retry_at == 1000.0
    assert r.last_error == ""
    assert r.payload == {"applicantId": "a1", "type": "applicantReviewed"}


def test_mark_delivered_sets_status_and_removes_from_due() -> None:
    adapter, _ = _make_adapter(start_time=1000.0)
    adapter.enqueue("ev-1", {"k": "v"}, "https://x")
    assert len(adapter.next_due(now_ts=1000.0, limit=10)) == 1
    adapter.mark_delivered("ev-1")
    assert adapter.next_due(now_ts=1000.0, limit=10) == []


def test_mark_failed_increments_attempt_and_schedules_backoff() -> None:
    adapter, clock = _make_adapter(start_time=1000.0)
    adapter.enqueue("ev-1", {}, "https://x")
    adapter.mark_failed("ev-1", error="upstream 500")
    # First failure: attempt -> 1, next_retry_at = now + backoff[0] = 1000 + 1
    due_now = adapter.next_due(now_ts=1000.0, limit=10)
    assert due_now == [], "should not be eligible immediately after backoff"
    due_later = adapter.next_due(now_ts=1001.0, limit=10)
    assert len(due_later) == 1
    r = due_later[0]
    assert r.attempt == 1
    assert r.status == "pending"
    assert r.last_error == "upstream 500"
    assert r.next_retry_at == 1001.0


def test_exponential_backoff_schedule_matches_expected() -> None:
    # ADR-034 default schedule: [1.0, 10.0, 60.0], max_attempts=3.
    adapter, clock = _make_adapter(start_time=0.0)
    adapter.enqueue("ev-1", {}, "https://x")

    # Attempt 1 fails @ t=0 → next_retry_at = 0 + 1 = 1
    adapter.mark_failed("ev-1", "err1")
    r1 = adapter.next_due(now_ts=1.0, limit=1)[0]
    assert r1.attempt == 1
    assert r1.next_retry_at == 1.0

    # Attempt 2 fails @ t=1 → next_retry_at = 1 + 10 = 11
    clock[0] = 1.0
    adapter.mark_failed("ev-1", "err2")
    r2 = adapter.next_due(now_ts=11.0, limit=1)[0]
    assert r2.attempt == 2
    assert r2.next_retry_at == 11.0

    # Attempt 3 fails @ t=11 → exhausted (max_attempts=3) → status=dead
    clock[0] = 11.0
    adapter.mark_failed("ev-1", "err3")
    assert adapter.next_due(now_ts=10_000.0, limit=10) == []


def test_max_attempts_marks_dead_and_excluded_from_due() -> None:
    adapter, clock = _make_adapter(
        start_time=0.0,
        backoff=(1.0, 1.0),
        max_attempts=2,
    )
    adapter.enqueue("ev-1", {}, "https://x")
    adapter.mark_failed("ev-1", "first")
    # Not dead yet: attempt=1 < max=2
    assert len(adapter.next_due(now_ts=10.0, limit=10)) == 1
    adapter.mark_failed("ev-1", "second")
    # attempt=2 == max → dead, excluded
    due = adapter.next_due(now_ts=10_000.0, limit=10)
    assert due == []
    # Underlying record reflects dead state with last_error
    rec = adapter._records["ev-1"]  # type: ignore[attr-defined]
    assert rec.status == "dead"
    assert rec.last_error == "second"
    assert rec.attempt == 2


def test_next_due_returns_only_eligible_records_ordered() -> None:
    adapter, clock = _make_adapter(start_time=100.0)
    # Three records, all enqueued at t=100 → eligible immediately
    adapter.enqueue("ev-a", {}, "https://x")
    adapter.enqueue("ev-b", {}, "https://x")
    adapter.enqueue("ev-c", {}, "https://x")
    # Fail ev-a at t=100 → next_retry_at = 101
    adapter.mark_failed("ev-a", "boom")
    # Mark ev-b delivered (excluded)
    adapter.mark_delivered("ev-b")
    # At t=100.5: ev-c is eligible (next_retry_at=100), ev-a not yet (101)
    due_mid = adapter.next_due(now_ts=100.5, limit=10)
    assert [r.event_id for r in due_mid] == ["ev-c"]
    # At t=101: ev-c (100) then ev-a (101); ev-b excluded (delivered)
    due_full = adapter.next_due(now_ts=101.0, limit=10)
    assert [r.event_id for r in due_full] == ["ev-c", "ev-a"]
    # Limit caps result
    due_capped = adapter.next_due(now_ts=101.0, limit=1)
    assert [r.event_id for r in due_capped] == ["ev-c"]
