"""
api/routers/support.py — Customer Support Block API
IL-CSB-01 | #115 | banxe-emi-stack

POST /v1/support/tickets         — create support ticket
GET  /v1/support/tickets         — list tickets (optionally filtered by customer_id)
GET  /v1/support/tickets/{id}    — get ticket detail
POST /v1/support/tickets/{id}/resolve — resolve a ticket
GET  /v1/support/metrics         — CSAT/NPS/SLA metrics (PS22/9 §10)

FCA compliance:
  - All tickets stored with SLA deadline (DISP 1.3)
  - Formal DISP complaints automatically triaged (DISP 1.1, 1.6)
  - Audit trail for every state change (I-24)
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from services.support.complaint_triage_agent import ComplaintTriageAgent
from services.support.customer_support_agent import CustomerSupportAgent
from services.support.escalation_agent import EscalationAgent
from services.support.feedback_analytics_agent import FeedbackAnalyticsAgent
from services.support.support_models import (
    InMemoryAuditPort,
    InMemoryCSATStore,
    InMemoryKBPort,
    InMemoryN8NPort,
    InMemoryTicketStore,
    SupportTicket,
    TicketCategory,
    TicketPriority,
    TicketStatus,
)
from services.support.ticket_routing_agent import TicketRoutingAgent

router = APIRouter(tags=["Support"])


# ─── Dependency injection ─────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _shared_ticket_store() -> InMemoryTicketStore:
    return InMemoryTicketStore()


@lru_cache(maxsize=1)
def _shared_audit() -> InMemoryAuditPort:
    return InMemoryAuditPort()


@lru_cache(maxsize=1)
def _shared_csat_store() -> InMemoryCSATStore:
    return InMemoryCSATStore()


def _get_routing_agent() -> TicketRoutingAgent:
    return TicketRoutingAgent(
        ticket_store=_shared_ticket_store(),
        audit=_shared_audit(),
    )


def _get_support_agent() -> CustomerSupportAgent:
    # Use low-confidence KB stub — auto-resolution happens only via
    # a real KB integration (production). In sandbox the FAQ bot escalates
    # all tickets to human agents unless a real KB is wired up.
    return CustomerSupportAgent(
        kb=InMemoryKBPort(
            answers=[
                {"text": "Please contact our support team for assistance.", "score": 0.30},
            ]
        ),
        ticket_store=_shared_ticket_store(),
        audit=_shared_audit(),
    )


def _get_escalation_agent() -> EscalationAgent:
    return EscalationAgent(
        ticket_store=_shared_ticket_store(),
        n8n=InMemoryN8NPort(),
        audit=_shared_audit(),
    )


def _get_triage_agent() -> ComplaintTriageAgent:
    return ComplaintTriageAgent(
        ticket_store=_shared_ticket_store(),
        n8n=InMemoryN8NPort(),
        audit=_shared_audit(),
    )


def _get_analytics_agent() -> FeedbackAnalyticsAgent:
    return FeedbackAnalyticsAgent(
        csat_store=_shared_csat_store(),
        audit=_shared_audit(),
    )


# ─── Request / Response models ────────────────────────────────────────────────


class CreateTicketRequest(BaseModel):
    customer_id: str = Field(..., description="Customer UUID")
    subject: str = Field(..., min_length=5, max_length=200)
    body: str = Field(..., min_length=10, max_length=5000)
    channel: str = Field(default="API", description="Originating channel")
    chatwoot_conversation_id: str | None = Field(
        default=None, description="Chatwoot conversation reference"
    )


class TicketResponse(BaseModel):
    id: str
    customer_id: str
    subject: str
    category: str
    priority: str
    status: str
    created_at: str
    sla_deadline: str
    assigned_to: str
    channel: str
    resolved_at: str | None
    resolution_summary: str
    auto_resolved: bool = False
    is_formal_complaint: bool = False


class ResolveTicketRequest(BaseModel):
    resolution_summary: str = Field(..., min_length=10, max_length=1000)
    csat_score: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="Customer satisfaction score 1-5 (if collected)",
    )
    nps_score: int | None = Field(
        default=None,
        ge=0,
        le=10,
        description="NPS score 0-10 (optional)",
    )


class MetricsResponse(BaseModel):
    period_days: int
    total_responses: int
    avg_csat: float | None
    avg_nps: float | None
    nps_score: float | None
    nps_promoters: int
    nps_detractors: int
    nps_passives: int
    by_category: dict[str, float]


def _ticket_to_response(ticket: SupportTicket) -> TicketResponse:
    return TicketResponse(
        id=ticket.id,
        customer_id=ticket.customer_id,
        subject=ticket.subject,
        category=ticket.category.value,
        priority=ticket.priority.value,
        status=ticket.status.value,
        created_at=ticket.created_at.isoformat(),
        sla_deadline=ticket.sla_deadline.isoformat(),
        assigned_to=ticket.assigned_to,
        channel=ticket.channel,
        resolved_at=ticket.resolved_at.isoformat() if ticket.resolved_at else None,
        resolution_summary=ticket.resolution_summary,
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post(
    "/support/tickets",
    response_model=TicketResponse,
    status_code=201,
    summary="Create support ticket",
)
async def create_ticket(
    body: CreateTicketRequest,
    routing_agent: TicketRoutingAgent = Depends(_get_routing_agent),
    support_agent: CustomerSupportAgent = Depends(_get_support_agent),
    triage_agent: ComplaintTriageAgent = Depends(_get_triage_agent),
) -> TicketResponse:
    """
    Create a support ticket, auto-route it, attempt FAQ auto-resolution,
    and check if it constitutes a formal DISP complaint.

    FCA DISP 1.3: tickets are SLA-stamped at creation time.
    FCA DISP 1.1: formal complaints are auto-detected and escalated.
    """
    ticket = SupportTicket.create(
        customer_id=body.customer_id,
        subject=body.subject,
        body=body.body,
        category=TicketCategory.GENERAL,
        priority=TicketPriority.LOW,
        channel=body.channel,
        chatwoot_conversation_id=body.chatwoot_conversation_id,
    )

    # Step 1: Route to correct queue + assign SLA
    await routing_agent.route(ticket)

    # Step 2: Attempt FAQ auto-resolution
    faq = await support_agent.handle(ticket)

    # Step 3: Triage for DISP formal complaint
    triage = await triage_agent.triage(ticket)

    resp = _ticket_to_response(ticket)
    resp.auto_resolved = faq.auto_resolved
    resp.is_formal_complaint = triage.is_formal_complaint
    return resp


@router.get(
    "/support/tickets",
    response_model=list[TicketResponse],
    summary="List open support tickets",
)
async def list_tickets(
    customer_id: Annotated[str | None, Query(description="Filter by customer ID")] = None,
) -> list[TicketResponse]:
    """List open support tickets. Optionally filter by customer_id."""
    store = _shared_ticket_store()
    tickets = await store.list_open(customer_id=customer_id)
    return [_ticket_to_response(t) for t in tickets]


@router.get(
    "/support/tickets/{ticket_id}",
    response_model=TicketResponse,
    summary="Get ticket detail",
)
async def get_ticket(ticket_id: str) -> TicketResponse:
    """Retrieve a single support ticket by ID."""
    store = _shared_ticket_store()
    ticket = await store.get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
    return _ticket_to_response(ticket)


@router.post(
    "/support/tickets/{ticket_id}/resolve",
    response_model=TicketResponse,
    summary="Resolve a support ticket",
)
async def resolve_ticket(
    ticket_id: str,
    body: ResolveTicketRequest,
    analytics_agent: FeedbackAnalyticsAgent = Depends(_get_analytics_agent),
) -> TicketResponse:
    """
    Mark a ticket as resolved and optionally record CSAT score.

    FCA DISP 1.3: resolution must be documented.
    PS22/9 §10: CSAT score feeds Consumer Duty outcome monitoring.
    """
    store = _shared_ticket_store()
    ticket = await store.get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
    if ticket.status in (TicketStatus.RESOLVED, TicketStatus.CLOSED):
        raise HTTPException(
            status_code=409,
            detail=f"Ticket {ticket_id} is already {ticket.status.value}",
        )

    await store.update_status(
        ticket_id,
        TicketStatus.RESOLVED,
        resolution_summary=body.resolution_summary,
        resolved_at=datetime.now(UTC),
    )

    # Reload ticket after status update
    updated = await store.get(ticket_id)
    if updated is None:
        raise HTTPException(status_code=500, detail="Failed to reload ticket after update")

    # Record CSAT if provided
    if body.csat_score is not None:
        await analytics_agent.submit_csat(
            updated,
            score=body.csat_score,
            nps_score=body.nps_score,
        )

    return _ticket_to_response(updated)


@router.get(
    "/support/metrics",
    response_model=MetricsResponse,
    summary="CSAT/NPS/SLA metrics (PS22/9 §10)",
)
async def get_metrics(
    period_days: Annotated[int, Query(ge=1, le=365, description="Rolling period in days")] = 30,
) -> MetricsResponse:
    """
    Aggregate CSAT and NPS metrics for Consumer Duty outcome testing.

    FCA PS22/9 §10: firms must monitor customer outcomes systematically.
    """
    agent = _get_analytics_agent()
    metrics = await agent.get_metrics(period_days=period_days)
    return MetricsResponse(
        period_days=metrics.period_days,
        total_responses=metrics.total_responses,
        avg_csat=metrics.avg_csat,
        avg_nps=metrics.avg_nps,
        nps_score=metrics.nps_score,
        nps_promoters=metrics.nps_promoters,
        nps_detractors=metrics.nps_detractors,
        nps_passives=metrics.nps_passives,
        by_category=metrics.by_category,
    )
