"""
tests/test_support/test_ticket_routing_agent.py
IL-CSB-01 | #118 | banxe-emi-stack — TicketRoutingAgent unit tests
"""

from __future__ import annotations

import pytest

from services.support.support_models import (
    InMemoryAuditPort,
    InMemoryTicketStore,
    SupportTicket,
    TicketCategory,
    TicketPriority,
    TicketStatus,
)
from services.support.ticket_routing_agent import TicketRoutingAgent

# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def agent() -> TicketRoutingAgent:
    return TicketRoutingAgent(
        ticket_store=InMemoryTicketStore(),
        audit=InMemoryAuditPort(),
    )


def _make_ticket(subject: str, body: str) -> SupportTicket:
    return SupportTicket.create(
        customer_id="cust-001",
        subject=subject,
        body=body,
        category=TicketCategory.GENERAL,
        priority=TicketPriority.LOW,
    )


# ─── Category routing ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_route_fraud_keyword_assigns_fraud_category(agent: TicketRoutingAgent) -> None:
    ticket = _make_ticket("Possible fraud on my account", "I see an unauthorized transaction")
    result = await agent.route(ticket)
    assert result.category == TicketCategory.FRAUD


@pytest.mark.asyncio
async def test_route_fraud_ticket_gets_critical_priority(agent: TicketRoutingAgent) -> None:
    ticket = _make_ticket("Fraud alert", "Stolen card used without my permission")
    result = await agent.route(ticket)
    assert result.priority == TicketPriority.CRITICAL


@pytest.mark.asyncio
async def test_route_fraud_assigned_to_fraud_team(agent: TicketRoutingAgent) -> None:
    ticket = _make_ticket("Fraud", "scam transaction")
    result = await agent.route(ticket)
    assert result.assigned_to == "fraud-team"


@pytest.mark.asyncio
async def test_route_payment_keyword_assigns_payment_category(agent: TicketRoutingAgent) -> None:
    ticket = _make_ticket("Payment issue", "My transfer is stuck as pending payment")
    result = await agent.route(ticket)
    assert result.category == TicketCategory.PAYMENT


@pytest.mark.asyncio
async def test_route_payment_gets_high_priority(agent: TicketRoutingAgent) -> None:
    ticket = _make_ticket("FPS transaction not received", "SEPA payment sent 2 days ago")
    result = await agent.route(ticket)
    assert result.priority == TicketPriority.HIGH


@pytest.mark.asyncio
async def test_route_kyc_keyword_assigns_kyc_category(agent: TicketRoutingAgent) -> None:
    ticket = _make_ticket("KYC verification problem", "My identity document was rejected")
    result = await agent.route(ticket)
    assert result.category == TicketCategory.KYC


@pytest.mark.asyncio
async def test_route_account_keyword_assigns_account_category(agent: TicketRoutingAgent) -> None:
    ticket = _make_ticket(
        "Account access issue", "I cannot login to my account, password not working"
    )
    result = await agent.route(ticket)
    assert result.category == TicketCategory.ACCOUNT


@pytest.mark.asyncio
async def test_route_general_fallback(agent: TicketRoutingAgent) -> None:
    ticket = _make_ticket("General inquiry", "I have a general question about fees")
    result = await agent.route(ticket)
    assert result.category == TicketCategory.GENERAL
    assert result.priority == TicketPriority.LOW


@pytest.mark.asyncio
async def test_route_general_auto_resolvable_faq(agent: TicketRoutingAgent) -> None:
    ticket = _make_ticket("What is the fee", "How do I know what charges apply?")
    result = await agent.route(ticket)
    assert result.auto_resolvable is True


@pytest.mark.asyncio
async def test_route_fraud_not_auto_resolvable(agent: TicketRoutingAgent) -> None:
    ticket = _make_ticket("Fraud", "unauthorized transaction")
    result = await agent.route(ticket)
    assert result.auto_resolvable is False


# ─── Confidence ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_route_returns_confidence_between_0_and_1(agent: TicketRoutingAgent) -> None:
    ticket = _make_ticket("Payment stuck", "My transfer is pending")
    result = await agent.route(ticket)
    assert 0.0 <= result.confidence <= 1.0


@pytest.mark.asyncio
async def test_route_multiple_keywords_increases_confidence(agent: TicketRoutingAgent) -> None:
    ticket = _make_ticket("Fraud scam stolen", "unauthorized chargeback dispute phishing")
    result = await agent.route(ticket)
    assert result.confidence >= 0.8


# ─── Persistence + audit ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_route_persists_ticket_to_store(agent: TicketRoutingAgent) -> None:
    store = InMemoryTicketStore()
    a = TicketRoutingAgent(ticket_store=store, audit=InMemoryAuditPort())
    ticket = _make_ticket("Account issue", "I cannot access my account")
    await a.route(ticket)
    saved = await store.get(ticket.id)
    assert saved is not None
    assert saved.id == ticket.id


@pytest.mark.asyncio
async def test_route_updates_ticket_status_to_in_progress(agent: TicketRoutingAgent) -> None:
    store = InMemoryTicketStore()
    a = TicketRoutingAgent(ticket_store=store, audit=InMemoryAuditPort())
    ticket = _make_ticket("Payment issue", "FPS transfer stuck")
    await a.route(ticket)
    saved = await store.get(ticket.id)
    assert saved is not None
    assert saved.status == TicketStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_route_logs_audit_event(agent: TicketRoutingAgent) -> None:
    audit = InMemoryAuditPort()
    a = TicketRoutingAgent(ticket_store=InMemoryTicketStore(), audit=audit)
    ticket = _make_ticket("Fraud on my account", "unauthorized payment")
    await a.route(ticket)
    assert len(audit.events) == 1
    assert audit.events[0]["event_type"] == "support.ticket_routed"


@pytest.mark.asyncio
async def test_route_audit_includes_customer_id(agent: TicketRoutingAgent) -> None:
    audit = InMemoryAuditPort()
    a = TicketRoutingAgent(ticket_store=InMemoryTicketStore(), audit=audit)
    ticket = _make_ticket("KYC problem", "document rejected")
    ticket.customer_id = "cust-audit-test"
    await a.route(ticket)
    assert audit.events[0]["payload"]["customer_id"] == "cust-audit-test"


# ─── SLA deadline ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_critical_ticket_sla_is_1_hour(agent: TicketRoutingAgent) -> None:
    from datetime import timedelta

    ticket = _make_ticket("Fraud", "Scam transaction stolen card")
    await agent.route(ticket)
    delta = ticket.sla_deadline - ticket.created_at
    assert timedelta(hours=0, minutes=50) < delta <= timedelta(hours=1, minutes=5)


@pytest.mark.asyncio
async def test_low_priority_sla_is_72_hours(agent: TicketRoutingAgent) -> None:
    from datetime import timedelta

    ticket = _make_ticket("General inquiry", "how do I change my name")
    await agent.route(ticket)
    delta = ticket.sla_deadline - ticket.created_at
    assert timedelta(hours=71) < delta <= timedelta(hours=73)
