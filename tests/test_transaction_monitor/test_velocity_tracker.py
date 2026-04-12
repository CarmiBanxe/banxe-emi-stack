"""
tests/test_transaction_monitor/test_velocity_tracker.py
IL-RTM-01 | banxe-emi-stack

Tests for InMemoryVelocityTracker: record, get_count, cumulative amount,
hard-block jurisdictions (I-02), EDD threshold (I-04).
"""

from __future__ import annotations

from decimal import Decimal

from services.transaction_monitor.models.transaction import TransactionEvent
from services.transaction_monitor.scoring.velocity_tracker import InMemoryVelocityTracker


def _make_event(
    amount: str = "1000.00",
    sender_id: str = "cust-001",
    sender_jurisdiction: str = "GB",
    receiver_jurisdiction: str | None = None,
) -> TransactionEvent:
    return TransactionEvent(
        transaction_id=f"TXN-{sender_id}-{amount}",
        amount=Decimal(amount),
        sender_id=sender_id,
        sender_jurisdiction=sender_jurisdiction,
        receiver_jurisdiction=receiver_jurisdiction,
    )


class TestInMemoryVelocityTracker:
    def test_record_increments_count(self):
        tracker = InMemoryVelocityTracker()
        event = _make_event(sender_id="cust-v1")
        tracker.record(event)
        assert tracker.get_count("cust-v1", "24h") == 1

    def test_multiple_records_accumulate(self):
        tracker = InMemoryVelocityTracker()
        for _ in range(5):
            tracker.record(_make_event(sender_id="cust-v2"))
        assert tracker.get_count("cust-v2", "24h") == 5

    def test_cumulative_amount_accumulates(self):
        tracker = InMemoryVelocityTracker()
        tracker.record(_make_event(amount="3000.00", sender_id="cust-v3"))
        tracker.record(_make_event(amount="4000.00", sender_id="cust-v3"))
        total = tracker.get_cumulative_amount("cust-v3", "24h")
        assert total == Decimal("7000.00")

    def test_hard_block_russian_jurisdiction(self):
        tracker = InMemoryVelocityTracker()
        event = _make_event(sender_jurisdiction="RU")
        assert tracker.is_hard_blocked(event) is True

    def test_hard_block_belarusian_jurisdiction(self):
        tracker = InMemoryVelocityTracker()
        event = _make_event(sender_jurisdiction="BY")
        assert tracker.is_hard_blocked(event) is True

    def test_no_hard_block_for_safe_jurisdiction(self):
        tracker = InMemoryVelocityTracker()
        event = _make_event(sender_jurisdiction="GB")
        assert tracker.is_hard_blocked(event) is False

    def test_edd_required_above_10k(self):
        tracker = InMemoryVelocityTracker()
        event = _make_event(amount="11000.00", sender_id="cust-edd")
        tracker.record(event)
        assert tracker.requires_edd("cust-edd") is True

    def test_edd_not_required_below_10k(self):
        tracker = InMemoryVelocityTracker()
        event = _make_event(amount="5000.00", sender_id="cust-no-edd")
        tracker.record(event)
        assert tracker.requires_edd("cust-no-edd") is False

    def test_zero_count_for_unknown_customer(self):
        tracker = InMemoryVelocityTracker()
        assert tracker.get_count("unknown-cust", "1h") == 0
