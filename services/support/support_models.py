"""
services/support/support_models.py — Shared data models for Customer Support Block
IL-CSB-01 | banxe-emi-stack

Shared across all support agents. Protocol DI ports for every external dep.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Protocol
import uuid

# ─── Enums ────────────────────────────────────────────────────────────────────


class TicketCategory(str, Enum):
    ACCOUNT = "ACCOUNT"
    PAYMENT = "PAYMENT"
    KYC = "KYC"
    FRAUD = "FRAUD"
    GENERAL = "GENERAL"


class TicketPriority(str, Enum):
    CRITICAL = "CRITICAL"  # SLA: 1h
    HIGH = "HIGH"  # SLA: 4h
    MEDIUM = "MEDIUM"  # SLA: 24h
    LOW = "LOW"  # SLA: 72h


class TicketStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_CUSTOMER = "AWAITING_CUSTOMER"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class EscalationReason(str, Enum):
    SLA_BREACH = "SLA_BREACH"
    CUSTOMER_REQUEST = "CUSTOMER_REQUEST"
    FRAUD_SUSPECTED = "FRAUD_SUSPECTED"
    COMPLAINT_REGULATORY = "COMPLAINT_REGULATORY"
    HITL_REQUIRED = "HITL_REQUIRED"


# SLA hours by priority (FCA DISP 1.3 — prompt handling)
SLA_HOURS: dict[TicketPriority, int] = {
    TicketPriority.CRITICAL: 1,
    TicketPriority.HIGH: 4,
    TicketPriority.MEDIUM: 24,
    TicketPriority.LOW: 72,
}


# ─── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class SupportTicket:
    id: str
    customer_id: str
    subject: str
    body: str
    category: TicketCategory
    priority: TicketPriority
    status: TicketStatus
    created_at: datetime
    sla_deadline: datetime
    assigned_to: str
    channel: str
    resolved_at: datetime | None = None
    resolution_summary: str = ""
    escalation_reason: EscalationReason | None = None
    chatwoot_conversation_id: str | None = None
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @classmethod
    def create(
        cls,
        customer_id: str,
        subject: str,
        body: str,
        category: TicketCategory,
        priority: TicketPriority,
        channel: str = "API",
        chatwoot_conversation_id: str | None = None,
    ) -> SupportTicket:
        now = datetime.now(UTC)
        sla_hours = SLA_HOURS[priority]
        return cls(
            id=str(uuid.uuid4()),
            customer_id=customer_id,
            subject=subject,
            body=body,
            category=category,
            priority=priority,
            status=TicketStatus.OPEN,
            created_at=now,
            sla_deadline=now + timedelta(hours=sla_hours),
            assigned_to="",
            channel=channel,
            chatwoot_conversation_id=chatwoot_conversation_id,
        )

    @property
    def is_sla_breached(self) -> bool:
        return datetime.now(UTC) > self.sla_deadline and self.status not in (
            TicketStatus.RESOLVED,
            TicketStatus.CLOSED,
        )

    @property
    def sla_remaining_seconds(self) -> float:
        delta = self.sla_deadline - datetime.now(UTC)
        return delta.total_seconds()


@dataclass(frozen=True)
class RoutingDecision:
    ticket_id: str
    category: TicketCategory
    priority: TicketPriority
    assigned_to: str
    auto_resolvable: bool
    confidence: float  # 0.0-1.0


@dataclass(frozen=True)
class FAQAnswer:
    ticket_id: str
    answer: str
    citations: list[str]
    confidence: float
    auto_resolved: bool


@dataclass(frozen=True)
class EscalationEvent:
    ticket_id: str
    customer_id: str
    reason: EscalationReason
    escalated_to: str
    escalated_at: datetime
    sla_deadline: datetime
    n8n_triggered: bool


@dataclass(frozen=True)
class CSATScore:
    ticket_id: str
    customer_id: str
    score: int  # 1-5
    nps_score: int | None  # 0-10 (NPS survey, optional)
    feedback_text: str
    submitted_at: datetime
    category: TicketCategory


@dataclass(frozen=True)
class FeedbackMetrics:
    period_days: int
    total_responses: int
    avg_csat: float | None
    avg_nps: float | None
    nps_promoters: int
    nps_detractors: int
    nps_passives: int
    nps_score: float | None  # (promoters - detractors) / total * 100
    by_category: dict[str, float]  # category → avg CSAT


# ─── Protocol ports ───────────────────────────────────────────────────────────


class TicketStorePort(Protocol):
    """Persist and retrieve support tickets."""

    async def save(self, ticket: SupportTicket) -> None: ...
    async def get(self, ticket_id: str) -> SupportTicket | None: ...
    async def list_open(self, customer_id: str | None = None) -> list[SupportTicket]: ...
    async def list_sla_breached(self) -> list[SupportTicket]: ...
    async def update_status(
        self,
        ticket_id: str,
        status: TicketStatus,
        resolution_summary: str = "",
        resolved_at: datetime | None = None,
    ) -> None: ...


class KBQueryPort(Protocol):
    """Query compliance knowledge base for FAQ answers."""

    async def query(self, question: str, collection: str = "banxe_faq") -> list[dict]: ...


class AuditPort(Protocol):
    """Append-only audit trail (I-24)."""

    async def log(self, event_type: str, payload: dict) -> None: ...


class N8NWebhookPort(Protocol):
    """Trigger n8n workflow webhooks."""

    async def trigger(self, event: str, payload: dict) -> bool: ...


class CSATStorePort(Protocol):
    """Persist and retrieve CSAT/NPS scores."""

    async def save_score(self, score: CSATScore) -> None: ...
    async def get_metrics(self, period_days: int = 30) -> FeedbackMetrics: ...


# ─── InMemory stubs (for tests) ───────────────────────────────────────────────


class InMemoryTicketStore:
    """InMemory stub for TicketStorePort — used in tests."""

    def __init__(self) -> None:
        self._tickets: dict[str, SupportTicket] = {}

    async def save(self, ticket: SupportTicket) -> None:
        self._tickets[ticket.id] = ticket

    async def get(self, ticket_id: str) -> SupportTicket | None:
        return self._tickets.get(ticket_id)

    async def list_open(self, customer_id: str | None = None) -> list[SupportTicket]:
        tickets = [
            t
            for t in self._tickets.values()
            if t.status not in (TicketStatus.RESOLVED, TicketStatus.CLOSED)
        ]
        if customer_id:
            tickets = [t for t in tickets if t.customer_id == customer_id]
        return tickets

    async def list_sla_breached(self) -> list[SupportTicket]:
        return [t for t in self._tickets.values() if t.is_sla_breached]

    async def update_status(
        self,
        ticket_id: str,
        status: TicketStatus,
        resolution_summary: str = "",
        resolved_at: datetime | None = None,
    ) -> None:
        if ticket_id in self._tickets:
            t = self._tickets[ticket_id]
            self._tickets[ticket_id] = SupportTicket(
                id=t.id,
                customer_id=t.customer_id,
                subject=t.subject,
                body=t.body,
                category=t.category,
                priority=t.priority,
                status=status,
                created_at=t.created_at,
                sla_deadline=t.sla_deadline,
                assigned_to=t.assigned_to,
                channel=t.channel,
                resolved_at=resolved_at or t.resolved_at,
                resolution_summary=resolution_summary or t.resolution_summary,
                escalation_reason=t.escalation_reason,
                chatwoot_conversation_id=t.chatwoot_conversation_id,
                correlation_id=t.correlation_id,
            )


class InMemoryKBPort:
    """InMemory stub for KBQueryPort — returns canned FAQ answers in tests."""

    def __init__(self, answers: list[dict] | None = None) -> None:
        # Use `is not None` check — empty list is valid (means "no KB results")
        self._answers = (
            answers
            if answers is not None
            else [
                {"text": "To reset your PIN use the app Settings > Security.", "score": 0.92},
                {"text": "Transfers are processed within 2 hours on business days.", "score": 0.85},
            ]
        )

    async def query(self, question: str, collection: str = "banxe_faq") -> list[dict]:  # noqa: ARG002
        return self._answers


class InMemoryAuditPort:
    """InMemory stub for AuditPort — collects events for test assertions."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def log(self, event_type: str, payload: dict) -> None:
        self.events.append({"event_type": event_type, "payload": payload})


class InMemoryN8NPort:
    """InMemory stub for N8NWebhookPort."""

    def __init__(self, should_succeed: bool = True) -> None:
        self._should_succeed = should_succeed
        self.triggered: list[dict] = []

    async def trigger(self, event: str, payload: dict) -> bool:
        self.triggered.append({"event": event, "payload": payload})
        return self._should_succeed


class InMemoryCSATStore:
    """InMemory stub for CSATStorePort."""

    def __init__(self) -> None:
        self._scores: list[CSATScore] = []

    async def save_score(self, score: CSATScore) -> None:
        self._scores.append(score)

    async def get_metrics(self, period_days: int = 30) -> FeedbackMetrics:
        since = datetime.now(UTC) - timedelta(days=period_days)
        recent = [s for s in self._scores if s.submitted_at >= since]
        if not recent:
            return FeedbackMetrics(
                period_days=period_days,
                total_responses=0,
                avg_csat=None,
                avg_nps=None,
                nps_promoters=0,
                nps_detractors=0,
                nps_passives=0,
                nps_score=None,
                by_category={},
            )
        avg_csat = sum(s.score for s in recent) / len(recent)
        nps_scores = [s.nps_score for s in recent if s.nps_score is not None]
        avg_nps = sum(nps_scores) / len(nps_scores) if nps_scores else None
        promoters = sum(1 for n in nps_scores if n >= 9)
        detractors = sum(1 for n in nps_scores if n <= 6)
        passives = len(nps_scores) - promoters - detractors
        total_nps = len(nps_scores)
        nps_score = (promoters - detractors) / total_nps * 100 if total_nps else None
        by_cat: dict[str, list[int]] = {}
        for s in recent:
            by_cat.setdefault(s.category.value, []).append(s.score)
        return FeedbackMetrics(
            period_days=period_days,
            total_responses=len(recent),
            avg_csat=avg_csat,
            avg_nps=avg_nps,
            nps_promoters=promoters,
            nps_detractors=detractors,
            nps_passives=passives,
            nps_score=nps_score,
            by_category={k: sum(v) / len(v) for k, v in by_cat.items()},
        )
