"""
services/support/escalation_agent.py — SLA Breach Monitor & Escalation Agent
IL-CSB-01 | #111 | banxe-emi-stack

Monitors open tickets for SLA breaches and escalates via:
  - n8n webhook (internal notification)
  - HITL queue (for CRITICAL/HIGH breaches requiring human decision)
  - FCA DISP 1.3 audit trail

FCA DISP 1.3: customer complaints and service issues must be handled promptly.
Escalation agent is the enforcement mechanism for SLA commitments.

Architecture: TicketStorePort + N8NWebhookPort + AuditPort Protocol DI
Trust Zone: AMBER (reads ticket PII, triggers human escalation)
Autonomy: L2 — auto-alerts, HITL for resolution decisions
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import os

from services.support.support_models import (
    AuditPort,
    EscalationEvent,
    EscalationReason,
    InMemoryAuditPort,
    InMemoryN8NPort,
    InMemoryTicketStore,
    N8NWebhookPort,
    SupportTicket,
    TicketPriority,
    TicketStatus,
    TicketStorePort,
)

logger = logging.getLogger(__name__)

N8N_ESCALATION_EVENT = os.environ.get("N8N_ESCALATION_EVENT", "support.sla_breach")

# Priorities that trigger HITL queue in addition to n8n notification
HITL_REQUIRED_PRIORITIES = {TicketPriority.CRITICAL, TicketPriority.HIGH}


class EscalationAgent:
    """
    Scans for SLA breaches and fires escalation workflows.

    run_scan() is intended to be called periodically (e.g., every 5 minutes
    via n8n schedule or cron). It returns all escalation events fired.

    Trust Zone: AMBER
    Autonomy: L2 (fires alerts + HITL queue, humans decide resolution)
    """

    def __init__(
        self,
        ticket_store: TicketStorePort | None = None,
        n8n: N8NWebhookPort | None = None,
        audit: AuditPort | None = None,
    ) -> None:
        self._store: TicketStorePort = ticket_store or InMemoryTicketStore()
        self._n8n: N8NWebhookPort = n8n or InMemoryN8NPort()
        self._audit: AuditPort = audit or InMemoryAuditPort()

    async def run_scan(self) -> list[EscalationEvent]:
        """
        Scan for SLA breaches and escalate.

        Returns list of EscalationEvents fired during this scan.
        FCA DISP 1.3 — every escalation is audit-logged.
        """
        breached = await self._store.list_sla_breached()
        events: list[EscalationEvent] = []

        for ticket in breached:
            event = await self._escalate(ticket, EscalationReason.SLA_BREACH)
            events.append(event)
            # Mark as ESCALATED so subsequent scans don't re-fire
            await self._store.update_status(ticket.id, TicketStatus.ESCALATED)

        if events:
            logger.info("Escalation scan: %d SLA breaches escalated", len(events))

        return events

    async def escalate_ticket(
        self,
        ticket: SupportTicket,
        reason: EscalationReason,
    ) -> EscalationEvent:
        """
        Manually escalate a specific ticket (e.g., customer request or fraud signal).

        FCA DISP 1.3: escalation path must be available on demand.
        """
        await self._store.update_status(ticket.id, TicketStatus.ESCALATED)
        return await self._escalate(ticket, reason)

    async def _escalate(
        self,
        ticket: SupportTicket,
        reason: EscalationReason,
    ) -> EscalationEvent:
        hitl_required = ticket.priority in HITL_REQUIRED_PRIORITIES
        escalated_to = "hitl-queue" if hitl_required else "human-support-team"

        payload = {
            "ticket_id": ticket.id,
            "customer_id": ticket.customer_id,
            "priority": ticket.priority.value,
            "category": ticket.category.value,
            "reason": reason.value,
            "sla_deadline": ticket.sla_deadline.isoformat(),
            "escalated_to": escalated_to,
            "hitl_required": hitl_required,
        }

        n8n_ok = await self._n8n.trigger(N8N_ESCALATION_EVENT, payload)

        await self._audit.log(
            "support.ticket_escalated",
            {
                **payload,
                "n8n_triggered": n8n_ok,
                "escalated_at": datetime.now(UTC).isoformat(),
            },
        )

        logger.warning(
            "ESCALATION: ticket=%s priority=%s reason=%s → %s",
            ticket.id,
            ticket.priority.value,
            reason.value,
            escalated_to,
        )

        return EscalationEvent(
            ticket_id=ticket.id,
            customer_id=ticket.customer_id,
            reason=reason,
            escalated_to=escalated_to,
            escalated_at=datetime.now(UTC),
            sla_deadline=ticket.sla_deadline,
            n8n_triggered=n8n_ok,
        )
