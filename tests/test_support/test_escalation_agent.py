"""
tests/test_support/test_escalation_agent.py
IL-CSB-01 | #118 | banxe-emi-stack — EscalationAgent unit tests
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from services.support.escalation_agent import EscalationAgent
from services.support.support_models import (
    EscalationReason,
    InMemoryAuditPort,
    InMemoryN8NPort,
    InMemoryTicketStore,
    SupportTicket,
    TicketCategory,
    TicketPriority,
    TicketStatus,
)

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_breached_ticket(priority: TicketPriority = TicketPriority.HIGH) -> SupportTicket:
    """Create a ticket with an SLA deadline already in the past."""
    t = SupportTicket.create(
        customer_id="cust-escalate",
        subject="Transfer stuck",
        body="My payment is stuck in pending",
        category=TicketCategory.PAYMENT,
        priority=priority,
    )
    # Force SLA breach
    t.sla_deadline = datetime.now(UTC) - timedelta(hours=1)
    return t


def _make_active_ticket(priority: TicketPriority = TicketPriority.MEDIUM) -> SupportTicket:
    """Create a ticket with SLA still valid."""
    return SupportTicket.create(
        customer_id="cust-active",
        subject="Account question",
        body="I have a question about my account",
        category=TicketCategory.ACCOUNT,
        priority=priority,
    )


# ─── SLA breach scan ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_scan_escalates_breached_ticket() -> None:
    store = InMemoryTicketStore()
    n8n = InMemoryN8NPort()
    agent = EscalationAgent(ticket_store=store, n8n=n8n, audit=InMemoryAuditPort())
    ticket = _make_breached_ticket()
    await store.save(ticket)
    events = await agent.run_scan()
    assert len(events) == 1
    assert events[0].ticket_id == ticket.id


@pytest.mark.asyncio
async def test_run_scan_no_breached_tickets_returns_empty() -> None:
    store = InMemoryTicketStore()
    agent = EscalationAgent(ticket_store=store, n8n=InMemoryN8NPort(), audit=InMemoryAuditPort())
    ticket = _make_active_ticket()
    await store.save(ticket)
    events = await agent.run_scan()
    assert events == []


@pytest.mark.asyncio
async def test_run_scan_marks_ticket_as_escalated() -> None:
    store = InMemoryTicketStore()
    agent = EscalationAgent(ticket_store=store, n8n=InMemoryN8NPort(), audit=InMemoryAuditPort())
    ticket = _make_breached_ticket()
    await store.save(ticket)
    await agent.run_scan()
    saved = await store.get(ticket.id)
    assert saved is not None
    assert saved.status == TicketStatus.ESCALATED


@pytest.mark.asyncio
async def test_run_scan_critical_priority_escalated_to_hitl_queue() -> None:
    store = InMemoryTicketStore()
    agent = EscalationAgent(ticket_store=store, n8n=InMemoryN8NPort(), audit=InMemoryAuditPort())
    ticket = _make_breached_ticket(priority=TicketPriority.CRITICAL)
    await store.save(ticket)
    events = await agent.run_scan()
    assert events[0].escalated_to == "hitl-queue"


@pytest.mark.asyncio
async def test_run_scan_low_priority_escalated_to_support_team() -> None:
    store = InMemoryTicketStore()
    agent = EscalationAgent(ticket_store=store, n8n=InMemoryN8NPort(), audit=InMemoryAuditPort())
    t = SupportTicket.create(
        customer_id="cust-low",
        subject="Low priority question",
        body="General question",
        category=TicketCategory.GENERAL,
        priority=TicketPriority.LOW,
    )
    t.sla_deadline = datetime.now(UTC) - timedelta(hours=1)
    await store.save(t)
    events = await agent.run_scan()
    assert events[0].escalated_to == "human-support-team"


# ─── n8n webhook ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_scan_triggers_n8n_webhook() -> None:
    store = InMemoryTicketStore()
    n8n = InMemoryN8NPort()
    agent = EscalationAgent(ticket_store=store, n8n=n8n, audit=InMemoryAuditPort())
    ticket = _make_breached_ticket()
    await store.save(ticket)
    await agent.run_scan()
    assert len(n8n.triggered) == 1
    assert n8n.triggered[0]["event"] == "support.sla_breach"


@pytest.mark.asyncio
async def test_escalation_event_includes_sla_deadline() -> None:
    store = InMemoryTicketStore()
    agent = EscalationAgent(ticket_store=store, n8n=InMemoryN8NPort(), audit=InMemoryAuditPort())
    ticket = _make_breached_ticket()
    await store.save(ticket)
    events = await agent.run_scan()
    assert events[0].sla_deadline == ticket.sla_deadline


@pytest.mark.asyncio
async def test_n8n_failure_still_returns_escalation_event() -> None:
    store = InMemoryTicketStore()
    n8n = InMemoryN8NPort(should_succeed=False)
    agent = EscalationAgent(ticket_store=store, n8n=n8n, audit=InMemoryAuditPort())
    ticket = _make_breached_ticket()
    await store.save(ticket)
    events = await agent.run_scan()
    assert len(events) == 1
    assert events[0].n8n_triggered is False


# ─── Manual escalation ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_escalate_ticket_manually_for_fraud() -> None:
    store = InMemoryTicketStore()
    agent = EscalationAgent(ticket_store=store, n8n=InMemoryN8NPort(), audit=InMemoryAuditPort())
    ticket = _make_active_ticket(priority=TicketPriority.CRITICAL)
    await store.save(ticket)
    event = await agent.escalate_ticket(ticket, EscalationReason.FRAUD_SUSPECTED)
    assert event.reason == EscalationReason.FRAUD_SUSPECTED


@pytest.mark.asyncio
async def test_escalate_ticket_sets_escalated_status() -> None:
    store = InMemoryTicketStore()
    agent = EscalationAgent(ticket_store=store, n8n=InMemoryN8NPort(), audit=InMemoryAuditPort())
    ticket = _make_active_ticket()
    await store.save(ticket)
    await agent.escalate_ticket(ticket, EscalationReason.CUSTOMER_REQUEST)
    saved = await store.get(ticket.id)
    assert saved is not None
    assert saved.status == TicketStatus.ESCALATED


# ─── Audit trail ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_escalation_logs_audit_event() -> None:
    store = InMemoryTicketStore()
    audit = InMemoryAuditPort()
    agent = EscalationAgent(ticket_store=store, n8n=InMemoryN8NPort(), audit=audit)
    ticket = _make_breached_ticket()
    await store.save(ticket)
    await agent.run_scan()
    event_types = [e["event_type"] for e in audit.events]
    assert "support.ticket_escalated" in event_types


@pytest.mark.asyncio
async def test_audit_event_contains_customer_id() -> None:
    store = InMemoryTicketStore()
    audit = InMemoryAuditPort()
    agent = EscalationAgent(ticket_store=store, n8n=InMemoryN8NPort(), audit=audit)
    ticket = _make_breached_ticket()
    await store.save(ticket)
    await agent.run_scan()
    payload = audit.events[0]["payload"]
    assert payload["customer_id"] == "cust-escalate"
