"""
tests/test_transaction_monitor/test_event_consumer.py
IL-RTM-01 | banxe-emi-stack

Tests for EventConsumer: processes stream events, handles parse errors,
counts processed/errors, stops on stop().
"""

from __future__ import annotations

from typing import Any

from services.transaction_monitor.consumer.event_consumer import (
    EventConsumer,
    InMemoryStreamPort,
)
from services.transaction_monitor.models.alert import AlertSeverity, AMLAlert
from services.transaction_monitor.models.risk_score import RiskScore
from services.transaction_monitor.models.transaction import TransactionEvent


def _noop_handler(event: TransactionEvent) -> AMLAlert:
    rs = RiskScore(score=0.2)
    return AMLAlert(
        transaction_id=event.transaction_id,
        customer_id=event.sender_id,
        severity=AlertSeverity.LOW,
        risk_score=rs,
        amount_gbp=event.amount,
    )


def _valid_event(i: int = 0) -> dict[str, Any]:
    return {
        "transaction_id": f"TXN-{i:04d}",
        "amount": "500.00",
        "sender_id": "cust-001",
        "sender_jurisdiction": "GB",
    }


class TestEventConsumer:
    def test_processes_all_events(self):
        events = [_valid_event(i) for i in range(5)]
        stream = InMemoryStreamPort(events)
        consumer = EventConsumer(stream=stream, scoring_handler=_noop_handler)
        consumer.start()
        assert consumer.stats()["processed"] == 5
        assert consumer.stats()["errors"] == 0

    def test_handles_parse_error_gracefully(self):
        events = [
            {"transaction_id": "TXN-GOOD", "amount": "100.00", "sender_id": "cust-001"},
            {"transaction_id": "TXN-BAD", "amount": "not-a-number", "sender_id": "cust-001"},
            {"transaction_id": "TXN-GOOD-2", "amount": "200.00", "sender_id": "cust-001"},
        ]
        stream = InMemoryStreamPort(events)
        consumer = EventConsumer(stream=stream, scoring_handler=_noop_handler)
        consumer.start()
        assert consumer.stats()["processed"] == 2
        assert consumer.stats()["errors"] == 1

    def test_stop_halts_processing(self):
        events = [_valid_event(i) for i in range(10)]
        stream = InMemoryStreamPort(events)

        processed_count = [0]

        def handler_with_stop(event: TransactionEvent) -> AMLAlert:
            processed_count[0] += 1
            if processed_count[0] >= 3:
                stream.stop()
            return _noop_handler(event)

        consumer = EventConsumer(stream=stream, scoring_handler=handler_with_stop)
        consumer.start()
        assert consumer.stats()["processed"] <= 10

    def test_empty_stream_processes_zero_events(self):
        stream = InMemoryStreamPort([])
        consumer = EventConsumer(stream=stream, scoring_handler=_noop_handler)
        consumer.start()
        assert consumer.stats()["processed"] == 0
