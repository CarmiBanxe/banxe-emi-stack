"""
tests/test_support/test_feedback_analytics_agent.py
IL-CSB-01 | #118 | banxe-emi-stack — FeedbackAnalyticsAgent unit tests
"""

from __future__ import annotations

import pytest

from services.support.feedback_analytics_agent import FeedbackAnalyticsAgent
from services.support.support_models import (
    InMemoryAuditPort,
    InMemoryCSATStore,
    SupportTicket,
    TicketCategory,
    TicketPriority,
    TicketStatus,
)

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_resolved_ticket(
    cust: str = "cust-csat", cat: TicketCategory = TicketCategory.ACCOUNT
) -> SupportTicket:
    t = SupportTicket.create(
        customer_id=cust,
        subject="Resolved ticket",
        body="My issue was resolved",
        category=cat,
        priority=TicketPriority.MEDIUM,
    )
    t.status = TicketStatus.RESOLVED
    return t


# ─── CSAT validation ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_csat_valid_score_succeeds() -> None:
    agent = FeedbackAnalyticsAgent(csat_store=InMemoryCSATStore(), audit=InMemoryAuditPort())
    ticket = _make_resolved_ticket()
    result = await agent.submit_csat(ticket, score=5)
    assert result.score == 5


@pytest.mark.asyncio
async def test_submit_csat_minimum_score_1_succeeds() -> None:
    agent = FeedbackAnalyticsAgent(csat_store=InMemoryCSATStore(), audit=InMemoryAuditPort())
    ticket = _make_resolved_ticket()
    result = await agent.submit_csat(ticket, score=1)
    assert result.score == 1


@pytest.mark.asyncio
async def test_submit_csat_score_0_raises_value_error() -> None:
    agent = FeedbackAnalyticsAgent(csat_store=InMemoryCSATStore(), audit=InMemoryAuditPort())
    ticket = _make_resolved_ticket()
    with pytest.raises(ValueError, match="1-5"):
        await agent.submit_csat(ticket, score=0)


@pytest.mark.asyncio
async def test_submit_csat_score_6_raises_value_error() -> None:
    agent = FeedbackAnalyticsAgent(csat_store=InMemoryCSATStore(), audit=InMemoryAuditPort())
    ticket = _make_resolved_ticket()
    with pytest.raises(ValueError, match="1-5"):
        await agent.submit_csat(ticket, score=6)


@pytest.mark.asyncio
async def test_submit_csat_unresolved_ticket_raises_value_error() -> None:
    agent = FeedbackAnalyticsAgent(csat_store=InMemoryCSATStore(), audit=InMemoryAuditPort())
    ticket = _make_resolved_ticket()
    ticket.status = TicketStatus.OPEN
    with pytest.raises(ValueError, match="resolved"):
        await agent.submit_csat(ticket, score=4)


@pytest.mark.asyncio
async def test_submit_csat_nps_score_0_to_10_succeeds() -> None:
    agent = FeedbackAnalyticsAgent(csat_store=InMemoryCSATStore(), audit=InMemoryAuditPort())
    ticket = _make_resolved_ticket()
    result = await agent.submit_csat(ticket, score=4, nps_score=9)
    assert result.nps_score == 9


@pytest.mark.asyncio
async def test_submit_csat_nps_score_11_raises_value_error() -> None:
    agent = FeedbackAnalyticsAgent(csat_store=InMemoryCSATStore(), audit=InMemoryAuditPort())
    ticket = _make_resolved_ticket()
    with pytest.raises(ValueError, match="0-10"):
        await agent.submit_csat(ticket, score=4, nps_score=11)


# ─── Metrics aggregation ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_metrics_no_responses_returns_nulls() -> None:
    agent = FeedbackAnalyticsAgent(csat_store=InMemoryCSATStore(), audit=InMemoryAuditPort())
    metrics = await agent.get_metrics(period_days=30)
    assert metrics.total_responses == 0
    assert metrics.avg_csat is None
    assert metrics.nps_score is None


@pytest.mark.asyncio
async def test_get_metrics_avg_csat_calculated_correctly() -> None:
    store = InMemoryCSATStore()
    agent = FeedbackAnalyticsAgent(csat_store=store, audit=InMemoryAuditPort())
    for score in [3, 4, 5]:
        ticket = _make_resolved_ticket()
        await agent.submit_csat(ticket, score=score)
    metrics = await agent.get_metrics()
    assert metrics.avg_csat == pytest.approx(4.0, abs=0.01)


@pytest.mark.asyncio
async def test_get_metrics_nps_promoter_count() -> None:
    store = InMemoryCSATStore()
    agent = FeedbackAnalyticsAgent(csat_store=store, audit=InMemoryAuditPort())
    for nps in [9, 10, 7, 5]:  # 2 promoters, 1 passive, 1 detractor
        ticket = _make_resolved_ticket()
        await agent.submit_csat(ticket, score=4, nps_score=nps)
    metrics = await agent.get_metrics()
    assert metrics.nps_promoters == 2
    assert metrics.nps_detractors == 1
    assert metrics.nps_passives == 1


@pytest.mark.asyncio
async def test_get_metrics_nps_score_formula() -> None:
    """NPS = (promoters - detractors) / total * 100."""
    store = InMemoryCSATStore()
    agent = FeedbackAnalyticsAgent(csat_store=store, audit=InMemoryAuditPort())
    # 3 promoters (9,10,9), 1 detractor (4), 0 passive → NPS = (3-1)/4 * 100 = 50
    for nps in [9, 10, 9, 4]:
        ticket = _make_resolved_ticket()
        await agent.submit_csat(ticket, score=4, nps_score=nps)
    metrics = await agent.get_metrics()
    assert metrics.nps_score == pytest.approx(50.0, abs=0.01)


@pytest.mark.asyncio
async def test_get_metrics_by_category_breakdown() -> None:
    store = InMemoryCSATStore()
    agent = FeedbackAnalyticsAgent(csat_store=store, audit=InMemoryAuditPort())
    for _ in range(2):
        ticket = _make_resolved_ticket(cat=TicketCategory.PAYMENT)
        await agent.submit_csat(ticket, score=5)
    for _ in range(2):
        ticket = _make_resolved_ticket(cat=TicketCategory.KYC)
        await agent.submit_csat(ticket, score=3)
    metrics = await agent.get_metrics()
    assert metrics.by_category.get("PAYMENT") == pytest.approx(5.0)
    assert metrics.by_category.get("KYC") == pytest.approx(3.0)


# ─── Audit trail ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_csat_logs_audit_event() -> None:
    audit = InMemoryAuditPort()
    agent = FeedbackAnalyticsAgent(csat_store=InMemoryCSATStore(), audit=audit)
    ticket = _make_resolved_ticket()
    await agent.submit_csat(ticket, score=4)
    event_types = [e["event_type"] for e in audit.events]
    assert "support.csat_submitted" in event_types


@pytest.mark.asyncio
async def test_submit_csat_audit_event_includes_regulation_reference() -> None:
    audit = InMemoryAuditPort()
    agent = FeedbackAnalyticsAgent(csat_store=InMemoryCSATStore(), audit=audit)
    ticket = _make_resolved_ticket()
    await agent.submit_csat(ticket, score=4)
    payload = audit.events[0]["payload"]
    assert "PS22/9" in payload["regulation"]


@pytest.mark.asyncio
async def test_submit_csat_positive_outcome_marked_correctly() -> None:
    audit = InMemoryAuditPort()
    agent = FeedbackAnalyticsAgent(csat_store=InMemoryCSATStore(), audit=audit)
    ticket = _make_resolved_ticket()
    await agent.submit_csat(ticket, score=4)
    payload = audit.events[0]["payload"]
    assert payload["positive_outcome"] is True


@pytest.mark.asyncio
async def test_submit_csat_negative_outcome_score_3() -> None:
    audit = InMemoryAuditPort()
    agent = FeedbackAnalyticsAgent(csat_store=InMemoryCSATStore(), audit=audit)
    ticket = _make_resolved_ticket()
    await agent.submit_csat(ticket, score=3)
    payload = audit.events[0]["payload"]
    assert payload["positive_outcome"] is False
