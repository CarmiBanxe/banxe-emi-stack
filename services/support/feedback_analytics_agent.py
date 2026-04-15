"""
services/support/feedback_analytics_agent.py — Feedback Analytics Agent
IL-CSB-01 | #113 | banxe-emi-stack

Collects and aggregates NPS / CSAT scores for resolved tickets.
Produces Consumer Duty PS22/9 §10 metrics for the FCA Outcome Testing dashboard.

PS22/9 §10 (Consumer Duty): firms must monitor and assess whether they are
achieving good outcomes, including tracking customer satisfaction.

Metrics produced:
  - CSAT (Customer Satisfaction Score): 1-5 per resolved ticket
  - NPS (Net Promoter Score): 0-10 per periodic survey
  - NPS score: (Promoters - Detractors) / Total × 100

Architecture: CSATStorePort Protocol DI
Trust Zone: RED (NPS/CSAT responses may contain PII in feedback_text)
Autonomy: L1 (fully automated data collection and aggregation)
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging

from services.support.support_models import (
    AuditPort,
    CSATScore,
    CSATStorePort,
    FeedbackMetrics,
    InMemoryAuditPort,
    InMemoryCSATStore,
    SupportTicket,
    TicketStatus,
)

logger = logging.getLogger(__name__)

# Minimum CSAT score to consider the ticket outcome "positive" (PS22/9 §10)
POSITIVE_OUTCOME_THRESHOLD = 4  # score ≥ 4 on 1-5 scale


class FeedbackAnalyticsAgent:
    """
    CSAT / NPS collection and aggregation.

    submit_csat() — called after ticket resolution (automated trigger from
                    ticket_routing_agent or manual agent).
    get_metrics()  — aggregates metrics over a rolling period for reporting.

    Trust Zone: RED (PII in free-text feedback)
    Autonomy: L1 (data collection + aggregation only, no decisions)
    """

    def __init__(
        self,
        csat_store: CSATStorePort | None = None,
        audit: AuditPort | None = None,
    ) -> None:
        self._store: CSATStorePort = csat_store or InMemoryCSATStore()
        self._audit: AuditPort = audit or InMemoryAuditPort()

    async def submit_csat(
        self,
        ticket: SupportTicket,
        score: int,
        nps_score: int | None = None,
        feedback_text: str = "",
    ) -> CSATScore:
        """
        Record a CSAT (and optionally NPS) response for a resolved ticket.

        Validation:
          - ticket must be RESOLVED or CLOSED
          - score: 1-5 (CSAT scale)
          - nps_score: 0-10 (NPS scale, optional)

        PS22/9 §10: every CSAT record contributes to Consumer Duty outcome monitoring.
        """
        if ticket.status not in (TicketStatus.RESOLVED, TicketStatus.CLOSED):
            msg = f"CSAT only valid for resolved tickets, got status={ticket.status}"
            raise ValueError(msg)
        if not 1 <= score <= 5:
            msg = f"CSAT score must be 1-5, got {score}"
            raise ValueError(msg)
        if nps_score is not None and not 0 <= nps_score <= 10:
            msg = f"NPS score must be 0-10, got {nps_score}"
            raise ValueError(msg)

        csat = CSATScore(
            ticket_id=ticket.id,
            customer_id=ticket.customer_id,
            score=score,
            nps_score=nps_score,
            feedback_text=feedback_text,
            submitted_at=datetime.now(UTC),
            category=ticket.category,
        )

        await self._store.save_score(csat)
        await self._audit.log(
            "support.csat_submitted",
            {
                "ticket_id": ticket.id,
                "customer_id": ticket.customer_id,
                "score": score,
                "nps_score": nps_score,
                "positive_outcome": score >= POSITIVE_OUTCOME_THRESHOLD,
                "category": ticket.category.value,
                "regulation": "PS22/9 §10",
            },
        )

        logger.info(
            "CSAT recorded: ticket=%s score=%d nps=%s outcome=%s",
            ticket.id,
            score,
            nps_score,
            "POSITIVE" if score >= POSITIVE_OUTCOME_THRESHOLD else "NEGATIVE",
        )

        return csat

    async def get_metrics(self, period_days: int = 30) -> FeedbackMetrics:
        """
        Aggregate CSAT/NPS metrics for the rolling period.

        Used by:
          - Consumer Duty PS22/9 §10 reporting
          - API endpoint GET /v1/support/metrics
          - MCP tool support_get_metrics

        Returns FeedbackMetrics with NPS components for FCA outcome testing.
        """
        metrics = await self._store.get_metrics(period_days=period_days)
        await self._audit.log(
            "support.metrics_queried",
            {
                "period_days": period_days,
                "total_responses": metrics.total_responses,
                "avg_csat": metrics.avg_csat,
                "nps_score": metrics.nps_score,
                "regulation": "PS22/9 §10",
            },
        )
        return metrics
