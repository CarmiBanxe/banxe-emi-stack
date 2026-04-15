"""
tests/test_support/test_support_models.py
IL-CSB-01 | #118 | banxe-emi-stack — SupportTicket model unit tests
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from services.support.support_models import (
    SLA_HOURS,
    CSATScore,
    InMemoryCSATStore,
    InMemoryTicketStore,
    SupportTicket,
    TicketCategory,
    TicketPriority,
    TicketStatus,
)

# ─── SupportTicket.create ────────────────────────────────────────────────────


def test_create_ticket_has_uuid_id() -> None:
    t = SupportTicket.create(
        "c1", "Subject", "Body text here long enough", TicketCategory.GENERAL, TicketPriority.LOW
    )
    assert len(t.id) == 36
    assert t.id.count("-") == 4


def test_create_ticket_status_is_open() -> None:
    t = SupportTicket.create(
        "c1", "Subject", "Body text here long enough", TicketCategory.GENERAL, TicketPriority.LOW
    )
    assert t.status == TicketStatus.OPEN


def test_create_ticket_sla_deadline_matches_priority_critical() -> None:
    t = SupportTicket.create(
        "c1", "Subject", "Body text here long enough", TicketCategory.FRAUD, TicketPriority.CRITICAL
    )
    expected_hours = SLA_HOURS[TicketPriority.CRITICAL]
    delta = t.sla_deadline - t.created_at
    assert abs(delta.total_seconds() - expected_hours * 3600) < 5


def test_create_ticket_sla_deadline_matches_priority_low() -> None:
    t = SupportTicket.create(
        "c1", "Subject", "Body text here long enough", TicketCategory.GENERAL, TicketPriority.LOW
    )
    expected_hours = SLA_HOURS[TicketPriority.LOW]
    delta = t.sla_deadline - t.created_at
    assert abs(delta.total_seconds() - expected_hours * 3600) < 5


def test_sla_hours_all_priorities_defined() -> None:
    for priority in TicketPriority:
        assert priority in SLA_HOURS


# ─── is_sla_breached ──────────────────────────────────────────────────────────


def test_is_sla_breached_false_for_active_ticket() -> None:
    t = SupportTicket.create(
        "c1", "Subject", "Body text here long enough", TicketCategory.GENERAL, TicketPriority.LOW
    )
    assert t.is_sla_breached is False


def test_is_sla_breached_true_for_past_deadline() -> None:
    t = SupportTicket.create(
        "c1", "Subject", "Body text here long enough", TicketCategory.GENERAL, TicketPriority.LOW
    )
    t.sla_deadline = datetime.now(UTC) - timedelta(hours=1)
    assert t.is_sla_breached is True


def test_is_sla_breached_false_for_resolved_ticket() -> None:
    t = SupportTicket.create(
        "c1", "Subject", "Body text here long enough", TicketCategory.GENERAL, TicketPriority.LOW
    )
    t.sla_deadline = datetime.now(UTC) - timedelta(hours=1)
    t.status = TicketStatus.RESOLVED
    assert t.is_sla_breached is False


# ─── InMemoryTicketStore ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_inmemory_store_save_and_get() -> None:
    store = InMemoryTicketStore()
    t = SupportTicket.create(
        "c1", "Subject", "Body text here long enough", TicketCategory.GENERAL, TicketPriority.LOW
    )
    await store.save(t)
    result = await store.get(t.id)
    assert result is not None
    assert result.id == t.id


@pytest.mark.asyncio
async def test_inmemory_store_get_nonexistent_returns_none() -> None:
    store = InMemoryTicketStore()
    result = await store.get("nonexistent-id")
    assert result is None


@pytest.mark.asyncio
async def test_inmemory_store_list_open_excludes_resolved() -> None:
    store = InMemoryTicketStore()
    open_t = SupportTicket.create(
        "c1",
        "Open ticket",
        "Body text here long enough",
        TicketCategory.GENERAL,
        TicketPriority.LOW,
    )
    resolved_t = SupportTicket.create(
        "c2",
        "Resolved ticket",
        "Body text here long enough",
        TicketCategory.GENERAL,
        TicketPriority.LOW,
    )
    resolved_t.status = TicketStatus.RESOLVED
    await store.save(open_t)
    await store.save(resolved_t)
    result = await store.list_open()
    ids = [t.id for t in result]
    assert open_t.id in ids
    assert resolved_t.id not in ids


@pytest.mark.asyncio
async def test_inmemory_store_list_open_filter_by_customer() -> None:
    store = InMemoryTicketStore()
    t1 = SupportTicket.create(
        "cust-A",
        "Ticket A",
        "Body text here long enough",
        TicketCategory.GENERAL,
        TicketPriority.LOW,
    )
    t2 = SupportTicket.create(
        "cust-B",
        "Ticket B",
        "Body text here long enough",
        TicketCategory.GENERAL,
        TicketPriority.LOW,
    )
    await store.save(t1)
    await store.save(t2)
    result = await store.list_open(customer_id="cust-A")
    assert all(t.customer_id == "cust-A" for t in result)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_inmemory_store_list_sla_breached() -> None:
    store = InMemoryTicketStore()
    t = SupportTicket.create(
        "c1", "Breached", "Body text here long enough", TicketCategory.GENERAL, TicketPriority.LOW
    )
    t.sla_deadline = datetime.now(UTC) - timedelta(hours=1)
    await store.save(t)
    result = await store.list_sla_breached()
    assert len(result) == 1


@pytest.mark.asyncio
async def test_inmemory_store_update_status() -> None:
    store = InMemoryTicketStore()
    t = SupportTicket.create(
        "c1", "Subject", "Body text here long enough", TicketCategory.GENERAL, TicketPriority.LOW
    )
    await store.save(t)
    await store.update_status(t.id, TicketStatus.RESOLVED, resolution_summary="Fixed!")
    saved = await store.get(t.id)
    assert saved is not None
    assert saved.status == TicketStatus.RESOLVED
    assert saved.resolution_summary == "Fixed!"


# ─── InMemoryCSATStore ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_csat_store_empty_metrics() -> None:
    store = InMemoryCSATStore()
    metrics = await store.get_metrics()
    assert metrics.total_responses == 0
    assert metrics.avg_csat is None


@pytest.mark.asyncio
async def test_csat_store_saves_and_counts() -> None:
    store = InMemoryCSATStore()
    score = CSATScore(
        ticket_id="t1",
        customer_id="c1",
        score=4,
        nps_score=8,
        feedback_text="Good service",
        submitted_at=datetime.now(UTC),
        category=TicketCategory.ACCOUNT,
    )
    await store.save_score(score)
    metrics = await store.get_metrics()
    assert metrics.total_responses == 1
    assert metrics.avg_csat == pytest.approx(4.0)
