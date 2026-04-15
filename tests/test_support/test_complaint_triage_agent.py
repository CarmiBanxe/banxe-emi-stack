"""
tests/test_support/test_complaint_triage_agent.py
IL-CSB-01 | #118 | banxe-emi-stack — ComplaintTriageAgent unit tests
"""

from __future__ import annotations

import pytest

from services.support.complaint_triage_agent import ComplaintTriageAgent
from services.support.support_models import (
    InMemoryAuditPort,
    InMemoryN8NPort,
    InMemoryTicketStore,
    SupportTicket,
    TicketCategory,
    TicketPriority,
    TicketStatus,
)


def _make_ticket(subject: str, body: str) -> SupportTicket:
    t = SupportTicket.create(
        customer_id="cust-triage",
        subject=subject,
        body=body,
        category=TicketCategory.GENERAL,
        priority=TicketPriority.MEDIUM,
    )
    return t


# ─── DISP complaint detection ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_explicit_complaint_word_is_formal_complaint() -> None:
    agent = ComplaintTriageAgent(
        ticket_store=InMemoryTicketStore(),
        n8n=InMemoryN8NPort(),
        audit=InMemoryAuditPort(),
    )
    ticket = _make_ticket(
        "Complaint about service", "I am making a formal complaint about your service"
    )
    result = await agent.triage(ticket)
    assert result.is_formal_complaint is True


@pytest.mark.asyncio
async def test_regulatory_rights_citation_is_formal_complaint() -> None:
    agent = ComplaintTriageAgent(
        ticket_store=InMemoryTicketStore(),
        n8n=InMemoryN8NPort(),
        audit=InMemoryAuditPort(),
    )
    ticket = _make_ticket("FCA complaint", "I will escalate this to the FCA regulator")
    result = await agent.triage(ticket)
    assert result.is_formal_complaint is True
    assert result.confidence >= 0.9


@pytest.mark.asyncio
async def test_financial_ombudsman_mention_is_formal_complaint() -> None:
    agent = ComplaintTriageAgent(
        ticket_store=InMemoryTicketStore(),
        n8n=InMemoryN8NPort(),
        audit=InMemoryAuditPort(),
    )
    ticket = _make_ticket("FOS complaint", "I will contact the Financial Ombudsman Service")
    result = await agent.triage(ticket)
    assert result.is_formal_complaint is True


@pytest.mark.asyncio
async def test_dissatisfaction_plus_financial_harm_is_complaint() -> None:
    agent = ComplaintTriageAgent(
        ticket_store=InMemoryTicketStore(),
        n8n=InMemoryN8NPort(),
        audit=InMemoryAuditPort(),
    )
    ticket = _make_ticket(
        "Very unhappy with service",
        "I am very unhappy and I want a refund for financial loss",
    )
    result = await agent.triage(ticket)
    assert result.is_formal_complaint is True


@pytest.mark.asyncio
async def test_neutral_inquiry_not_a_formal_complaint() -> None:
    agent = ComplaintTriageAgent(
        ticket_store=InMemoryTicketStore(),
        n8n=InMemoryN8NPort(),
        audit=InMemoryAuditPort(),
    )
    ticket = _make_ticket("How do I reset my PIN?", "I forgot my PIN code")
    result = await agent.triage(ticket)
    assert result.is_formal_complaint is False


@pytest.mark.asyncio
async def test_payment_question_not_a_formal_complaint() -> None:
    agent = ComplaintTriageAgent(
        ticket_store=InMemoryTicketStore(),
        n8n=InMemoryN8NPort(),
        audit=InMemoryAuditPort(),
    )
    ticket = _make_ticket("Transfer time", "When will my transfer arrive?")
    result = await agent.triage(ticket)
    assert result.is_formal_complaint is False


# ─── DISP category ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_regulatory_rights_category_assigned() -> None:
    agent = ComplaintTriageAgent(
        ticket_store=InMemoryTicketStore(),
        n8n=InMemoryN8NPort(),
        audit=InMemoryAuditPort(),
    )
    ticket = _make_ticket("FCA complaint", "I will go to the FCA regulator")
    result = await agent.triage(ticket)
    assert result.disp_category == "REGULATORY_RIGHTS"


@pytest.mark.asyncio
async def test_service_dissatisfaction_category_assigned() -> None:
    agent = ComplaintTriageAgent(
        ticket_store=InMemoryTicketStore(),
        n8n=InMemoryN8NPort(),
        audit=InMemoryAuditPort(),
    )
    ticket = _make_ticket("Terrible service", "I am very dissatisfied with the service")
    result = await agent.triage(ticket)
    assert result.is_formal_complaint is True
    assert result.disp_category in ("SERVICE_DISSATISFACTION", "FINANCIAL_DISSATISFACTION")


# ─── State changes + n8n ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_formal_complaint_escalates_ticket_status() -> None:
    store = InMemoryTicketStore()
    agent = ComplaintTriageAgent(
        ticket_store=store,
        n8n=InMemoryN8NPort(),
        audit=InMemoryAuditPort(),
    )
    ticket = _make_ticket("Complaint", "I am making a formal complaint")
    await store.save(ticket)
    await agent.triage(ticket)
    saved = await store.get(ticket.id)
    assert saved is not None
    assert saved.status == TicketStatus.ESCALATED


@pytest.mark.asyncio
async def test_formal_complaint_triggers_n8n_webhook() -> None:
    n8n = InMemoryN8NPort()
    agent = ComplaintTriageAgent(
        ticket_store=InMemoryTicketStore(),
        n8n=n8n,
        audit=InMemoryAuditPort(),
    )
    ticket = _make_ticket(
        "Formal complaint", "I want to complain about your service, this is unacceptable"
    )
    result = await agent.triage(ticket)
    assert result.is_formal_complaint is True
    assert len(n8n.triggered) == 1
    assert n8n.triggered[0]["event"] == "support.formal_complaint_triaged"


@pytest.mark.asyncio
async def test_non_complaint_does_not_trigger_n8n() -> None:
    n8n = InMemoryN8NPort()
    agent = ComplaintTriageAgent(
        ticket_store=InMemoryTicketStore(),
        n8n=n8n,
        audit=InMemoryAuditPort(),
    )
    ticket = _make_ticket("PIN reset help", "How do I reset my PIN?")
    await agent.triage(ticket)
    assert len(n8n.triggered) == 0


# ─── Audit trail ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_formal_complaint_logs_audit_event() -> None:
    audit = InMemoryAuditPort()
    agent = ComplaintTriageAgent(
        ticket_store=InMemoryTicketStore(),
        n8n=InMemoryN8NPort(),
        audit=audit,
    )
    ticket = _make_ticket("Complaint", "I am formally complaining about your service")
    await agent.triage(ticket)
    event_types = [e["event_type"] for e in audit.events]
    assert "support.formal_complaint_created" in event_types


@pytest.mark.asyncio
async def test_non_complaint_triage_also_audit_logged() -> None:
    audit = InMemoryAuditPort()
    agent = ComplaintTriageAgent(
        ticket_store=InMemoryTicketStore(),
        n8n=InMemoryN8NPort(),
        audit=audit,
    )
    ticket = _make_ticket("PIN question", "How do I reset my PIN?")
    await agent.triage(ticket)
    event_types = [e["event_type"] for e in audit.events]
    assert "support.complaint_triage_not_disp" in event_types


@pytest.mark.asyncio
async def test_audit_event_includes_regulation_reference() -> None:
    audit = InMemoryAuditPort()
    agent = ComplaintTriageAgent(
        ticket_store=InMemoryTicketStore(),
        n8n=InMemoryN8NPort(),
        audit=audit,
    )
    ticket = _make_ticket("Complaint", "I am making a formal complaint")
    await agent.triage(ticket)
    # Find complaint_created event
    complaint_events = [
        e for e in audit.events if e["event_type"] == "support.formal_complaint_created"
    ]
    assert len(complaint_events) == 1
    assert "DISP" in complaint_events[0]["payload"]["regulation"]
