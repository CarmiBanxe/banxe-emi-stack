"""
test_event_bus.py — Event Bus tests
S17-11: Async inter-department domain events
"""

from __future__ import annotations

import pytest

from services.events.event_bus import (
    BanxeEventType,
    DomainEvent,
    InMemoryEventBus,
)


@pytest.fixture
def bus():
    return InMemoryEventBus()


def _payment_event(customer_id: str = "cust-001") -> DomainEvent:
    return DomainEvent.create(
        event_type=BanxeEventType.PAYMENT_COMPLETED,
        source_service="payment_service",
        payload={"amount": "100.00", "currency": "GBP", "rail": "FPS"},
        customer_id=customer_id,
    )


def _kyc_event() -> DomainEvent:
    return DomainEvent.create(
        event_type=BanxeEventType.KYC_APPROVED,
        source_service="kyc_service",
        payload={"risk_level": "low"},
        customer_id="cust-001",
    )


# ── Event creation ─────────────────────────────────────────────────────────────


class TestDomainEvent:
    def test_event_id_assigned(self):
        e = _payment_event()
        assert len(e.event_id) == 36  # UUID4

    def test_occurred_at_utc(self):
        e = _payment_event()
        assert e.occurred_at.tzinfo is not None

    def test_to_json_roundtrip(self):
        import json

        e = _payment_event()
        data = json.loads(e.to_json())
        assert data["event_type"] == BanxeEventType.PAYMENT_COMPLETED.value
        assert data["customer_id"] == "cust-001"
        assert data["payload"]["currency"] == "GBP"

    def test_correlation_id(self):
        e = DomainEvent.create(
            event_type=BanxeEventType.PAYMENT_INITIATED,
            source_service="payment_service",
            payload={},
            correlation_id="flow-abc",
        )
        assert e.correlation_id == "flow-abc"


# ── Publish + subscribe ────────────────────────────────────────────────────────


class TestInMemoryEventBus:
    def test_publish_stores_event(self, bus):
        e = _payment_event()
        bus.publish(e)
        assert len(bus.all_events) == 1

    def test_subscribe_handler_called(self, bus):
        received = []
        bus.subscribe(BanxeEventType.PAYMENT_COMPLETED, lambda ev: received.append(ev))
        bus.publish(_payment_event())
        assert len(received) == 1
        assert received[0].event_type == BanxeEventType.PAYMENT_COMPLETED

    def test_handler_not_called_for_other_type(self, bus):
        received = []
        bus.subscribe(BanxeEventType.KYC_APPROVED, lambda ev: received.append(ev))
        bus.publish(_payment_event())
        assert len(received) == 0

    def test_multiple_handlers(self, bus):
        calls = []
        bus.subscribe(BanxeEventType.PAYMENT_COMPLETED, lambda ev: calls.append("h1"))
        bus.subscribe(BanxeEventType.PAYMENT_COMPLETED, lambda ev: calls.append("h2"))
        bus.publish(_payment_event())
        assert "h1" in calls
        assert "h2" in calls

    def test_failing_handler_does_not_abort(self, bus):
        def bad_handler(ev: DomainEvent) -> None:
            raise RuntimeError("handler error")

        good_calls = []
        bus.subscribe(BanxeEventType.PAYMENT_COMPLETED, bad_handler)
        bus.subscribe(BanxeEventType.PAYMENT_COMPLETED, lambda ev: good_calls.append(ev))
        bus.publish(_payment_event())
        assert len(good_calls) == 1  # good handler still ran

    def test_events_of_type(self, bus):
        bus.publish(_payment_event())
        bus.publish(_payment_event())
        bus.publish(_kyc_event())
        payments = bus.events_of_type(BanxeEventType.PAYMENT_COMPLETED)
        kycs = bus.events_of_type(BanxeEventType.KYC_APPROVED)
        assert len(payments) == 2
        assert len(kycs) == 1

    def test_clear_resets(self, bus):
        bus.publish(_payment_event())
        bus.clear()
        assert len(bus.all_events) == 0

    def test_multiple_customers(self, bus):
        bus.publish(_payment_event("cust-001"))
        bus.publish(_payment_event("cust-002"))
        all_ev = bus.all_events
        customers = {e.customer_id for e in all_ev}
        assert customers == {"cust-001", "cust-002"}


# ── All event types defined ────────────────────────────────────────────────────


class TestEventTypes:
    def test_payment_event_types(self):
        types = [t.value for t in BanxeEventType]
        assert "payment.completed" in types
        assert "payment.failed" in types
        assert "kyc.approved" in types
        assert "safeguarding.shortfall" in types
        assert "agreement.signed" in types
        assert "reporting.fin060_generated" in types

    def test_publish_all_event_types(self, bus):
        """Smoke test: all event types can be published."""
        for event_type in BanxeEventType:
            e = DomainEvent.create(
                event_type=event_type,
                source_service="test",
                payload={},
            )
            bus.publish(e)
        assert len(bus.all_events) == len(BanxeEventType)
