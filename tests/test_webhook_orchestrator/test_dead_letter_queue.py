"""
tests/test_webhook_orchestrator/test_dead_letter_queue.py — DeadLetterQueue tests
IL-WHO-01 | Phase 28 | banxe-emi-stack

12 tests: enqueue (sets DEAD_LETTER), list_dlq, retry_from_dlq creates new PENDING
(old remains), dlq_stats counts by subscription.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from services.webhook_orchestrator.dead_letter_queue import DeadLetterQueue
from services.webhook_orchestrator.models import (
    DeliveryAttempt,
    DeliveryStatus,
    InMemoryDeliveryStore,
)

NOW = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)


def make_attempt(
    attempt_id: str = "att-1",
    event_id: str = "evt-1",
    sub_id: str = "sub-1",
    status: DeliveryStatus = DeliveryStatus.FAILED,
) -> DeliveryAttempt:
    return DeliveryAttempt(
        attempt_id=attempt_id,
        event_id=event_id,
        subscription_id=sub_id,
        status=status,
        http_status=None,
        attempt_number=6,
        response_body="Connection refused",
        attempted_at=NOW,
    )


def make_dlq() -> tuple[DeadLetterQueue, InMemoryDeliveryStore]:
    store = InMemoryDeliveryStore()
    dlq = DeadLetterQueue(delivery_store=store)
    return dlq, store


class TestEnqueue:
    def test_enqueue_sets_dead_letter_status(self) -> None:
        dlq, store = make_dlq()
        attempt = make_attempt()
        store.save(attempt)
        result = dlq.enqueue(attempt)
        assert result.status == DeliveryStatus.DEAD_LETTER

    def test_enqueue_persists_to_store(self) -> None:
        dlq, store = make_dlq()
        attempt = make_attempt()
        store.save(attempt)
        dlq.enqueue(attempt)
        stored = store.get("att-1")
        assert stored is not None
        assert stored.status == DeliveryStatus.DEAD_LETTER

    def test_enqueue_returns_dead_letter_attempt(self) -> None:
        dlq, store = make_dlq()
        attempt = make_attempt()
        store.save(attempt)
        result = dlq.enqueue(attempt)
        assert result.attempt_id == "att-1"


class TestListDlq:
    def test_list_dlq_returns_dead_letter_only(self) -> None:
        dlq, store = make_dlq()
        dead = make_attempt("att-1")
        store.save(dead)
        dlq.enqueue(dead)
        delivered = replace(make_attempt("att-2"), status=DeliveryStatus.DELIVERED)
        store.save(delivered)
        result = dlq.list_dlq()
        assert len(result) == 1
        assert result[0].status == DeliveryStatus.DEAD_LETTER

    def test_list_dlq_empty_when_no_dead_letters(self) -> None:
        dlq, store = make_dlq()
        result = dlq.list_dlq()
        assert result == []

    def test_list_dlq_multiple_entries(self) -> None:
        dlq, store = make_dlq()
        for i in range(3):
            a = make_attempt(f"att-{i}")
            store.save(a)
            dlq.enqueue(a)
        result = dlq.list_dlq()
        assert len(result) == 3


class TestRetryFromDlq:
    def test_retry_creates_new_pending_attempt(self) -> None:
        dlq, store = make_dlq()
        attempt = make_attempt()
        store.save(attempt)
        dlq.enqueue(attempt)
        new_attempt = dlq.retry_from_dlq("att-1")
        assert new_attempt.status == DeliveryStatus.PENDING

    def test_retry_creates_attempt_number_1(self) -> None:
        dlq, store = make_dlq()
        attempt = make_attempt()
        store.save(attempt)
        dlq.enqueue(attempt)
        new_attempt = dlq.retry_from_dlq("att-1")
        assert new_attempt.attempt_number == 1

    def test_retry_old_dlq_entry_remains(self) -> None:
        dlq, store = make_dlq()
        attempt = make_attempt()
        store.save(attempt)
        dlq.enqueue(attempt)
        dlq.retry_from_dlq("att-1")
        original = store.get("att-1")
        assert original is not None
        assert original.status == DeliveryStatus.DEAD_LETTER

    def test_retry_new_attempt_different_id(self) -> None:
        dlq, store = make_dlq()
        attempt = make_attempt()
        store.save(attempt)
        dlq.enqueue(attempt)
        new_attempt = dlq.retry_from_dlq("att-1")
        assert new_attempt.attempt_id != "att-1"

    def test_retry_missing_attempt_raises(self) -> None:
        dlq, _ = make_dlq()
        with pytest.raises(ValueError, match="not found"):
            dlq.retry_from_dlq("does-not-exist")

    def test_retry_non_dead_letter_raises(self) -> None:
        dlq, store = make_dlq()
        attempt = replace(make_attempt(), status=DeliveryStatus.PENDING)
        store.save(attempt)
        with pytest.raises(ValueError, match="DEAD_LETTER"):
            dlq.retry_from_dlq("att-1")


class TestDlqStats:
    def test_stats_total_count(self) -> None:
        dlq, store = make_dlq()
        for i in range(3):
            a = make_attempt(f"att-{i}", sub_id="sub-1")
            store.save(a)
            dlq.enqueue(a)
        stats = dlq.get_dlq_stats()
        assert stats["total_dead_letter"] == 3

    def test_stats_by_subscription(self) -> None:
        dlq, store = make_dlq()
        for i in range(2):
            a = make_attempt(f"att-sub1-{i}", sub_id="sub-1")
            store.save(a)
            dlq.enqueue(a)
        a3 = make_attempt("att-sub2-0", sub_id="sub-2")
        store.save(a3)
        dlq.enqueue(a3)
        stats = dlq.get_dlq_stats()
        assert stats["by_subscription"]["sub-1"] == 2
        assert stats["by_subscription"]["sub-2"] == 1

    def test_stats_empty_dlq(self) -> None:
        dlq, _ = make_dlq()
        stats = dlq.get_dlq_stats()
        assert stats["total_dead_letter"] == 0
        assert stats["by_subscription"] == {}
