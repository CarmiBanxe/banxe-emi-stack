"""
tests/test_support/test_customer_support_agent.py
IL-CSB-01 | #118 | banxe-emi-stack — CustomerSupportAgent unit tests
"""

from __future__ import annotations

import pytest

from services.support.customer_support_agent import CustomerSupportAgent
from services.support.support_models import (
    InMemoryAuditPort,
    InMemoryKBPort,
    InMemoryTicketStore,
    SupportTicket,
    TicketCategory,
    TicketPriority,
    TicketStatus,
)

# ─── Fixtures ────────────────────────────────────────────────────────────────


def _make_resolved_ticket() -> SupportTicket:
    t = SupportTicket.create(
        customer_id="cust-002",
        subject="How do I reset my PIN?",
        body="I forgot my PIN and need to reset it",
        category=TicketCategory.ACCOUNT,
        priority=TicketPriority.MEDIUM,
    )
    return t


# ─── Auto-resolution ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_high_confidence_answer_auto_resolves_ticket() -> None:
    kb = InMemoryKBPort(answers=[{"text": "Reset PIN in app Settings > Security.", "score": 0.92}])
    store = InMemoryTicketStore()
    agent = CustomerSupportAgent(kb=kb, ticket_store=store, audit=InMemoryAuditPort())
    ticket = _make_resolved_ticket()
    await store.save(ticket)
    result = await agent.handle(ticket)
    assert result.auto_resolved is True


@pytest.mark.asyncio
async def test_auto_resolved_ticket_status_is_resolved() -> None:
    kb = InMemoryKBPort(answers=[{"text": "PIN reset steps.", "score": 0.95}])
    store = InMemoryTicketStore()
    agent = CustomerSupportAgent(kb=kb, ticket_store=store, audit=InMemoryAuditPort())
    ticket = _make_resolved_ticket()
    await store.save(ticket)
    await agent.handle(ticket)
    saved = await store.get(ticket.id)
    assert saved is not None
    assert saved.status == TicketStatus.RESOLVED


@pytest.mark.asyncio
async def test_auto_resolved_resolution_summary_contains_confidence() -> None:
    kb = InMemoryKBPort(answers=[{"text": "Answer text.", "score": 0.91}])
    store = InMemoryTicketStore()
    agent = CustomerSupportAgent(kb=kb, ticket_store=store, audit=InMemoryAuditPort())
    ticket = _make_resolved_ticket()
    await store.save(ticket)
    await agent.handle(ticket)
    saved = await store.get(ticket.id)
    assert saved is not None
    assert "confidence=0.91" in saved.resolution_summary


@pytest.mark.asyncio
async def test_low_confidence_answer_not_auto_resolved() -> None:
    kb = InMemoryKBPort(answers=[{"text": "Maybe try support.", "score": 0.50}])
    store = InMemoryTicketStore()
    agent = CustomerSupportAgent(kb=kb, ticket_store=store, audit=InMemoryAuditPort())
    ticket = _make_resolved_ticket()
    await store.save(ticket)
    result = await agent.handle(ticket)
    assert result.auto_resolved is False


@pytest.mark.asyncio
async def test_low_confidence_ticket_remains_in_progress() -> None:
    kb = InMemoryKBPort(answers=[{"text": "Maybe try support.", "score": 0.30}])
    store = InMemoryTicketStore()
    agent = CustomerSupportAgent(kb=kb, ticket_store=store, audit=InMemoryAuditPort())
    ticket = _make_resolved_ticket()
    await store.save(ticket)
    await agent.handle(ticket)
    saved = await store.get(ticket.id)
    assert saved is not None
    assert saved.status == TicketStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_empty_kb_results_escalates_to_human() -> None:
    kb = InMemoryKBPort(answers=[])
    store = InMemoryTicketStore()
    agent = CustomerSupportAgent(kb=kb, ticket_store=store, audit=InMemoryAuditPort())
    ticket = _make_resolved_ticket()
    await store.save(ticket)
    result = await agent.handle(ticket)
    assert result.auto_resolved is False
    assert result.confidence == 0.0


# ─── Answer content ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_returns_answer_text() -> None:
    kb = InMemoryKBPort(answers=[{"text": "Go to Settings > PIN.", "score": 0.88}])
    agent = CustomerSupportAgent(
        kb=kb, ticket_store=InMemoryTicketStore(), audit=InMemoryAuditPort()
    )
    ticket = _make_resolved_ticket()
    result = await agent.handle(ticket)
    assert result.answer == "Go to Settings > PIN."


@pytest.mark.asyncio
async def test_handle_returns_citations() -> None:
    kb = InMemoryKBPort(
        answers=[
            {"text": "PIN help.", "score": 0.90, "source": "faq-pin-001"},
            {"text": "More info.", "score": 0.80, "source": "faq-pin-002"},
        ]
    )
    agent = CustomerSupportAgent(
        kb=kb, ticket_store=InMemoryTicketStore(), audit=InMemoryAuditPort()
    )
    ticket = _make_resolved_ticket()
    result = await agent.handle(ticket)
    assert "faq-pin-001" in result.citations


# ─── Audit trail ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_auto_resolve_logs_audit_event() -> None:
    kb = InMemoryKBPort(answers=[{"text": "Answer.", "score": 0.95}])
    audit = InMemoryAuditPort()
    store = InMemoryTicketStore()
    agent = CustomerSupportAgent(kb=kb, ticket_store=store, audit=audit)
    ticket = _make_resolved_ticket()
    await store.save(ticket)
    await agent.handle(ticket)
    event_types = [e["event_type"] for e in audit.events]
    assert "support.ticket_auto_resolved" in event_types


@pytest.mark.asyncio
async def test_escalation_logs_audit_event() -> None:
    kb = InMemoryKBPort(answers=[{"text": "Vague.", "score": 0.40}])
    audit = InMemoryAuditPort()
    agent = CustomerSupportAgent(kb=kb, ticket_store=InMemoryTicketStore(), audit=audit)
    ticket = _make_resolved_ticket()
    await agent.handle(ticket)
    event_types = [e["event_type"] for e in audit.events]
    assert "support.faq_escalated_to_human" in event_types
