"""
services/support/customer_support_agent.py — Customer Support FAQ Agent
IL-CSB-01 | #110 | banxe-emi-stack

RAG-powered FAQ bot that answers common support questions from the Compliance KB.
Reuses KBQueryPort (same Protocol as compliance_kb service).

Decision logic:
  confidence ≥ AUTO_RESOLVE_THRESHOLD → auto-resolve ticket, return answer
  confidence < AUTO_RESOLVE_THRESHOLD → escalate to human agent

Architecture: KBQueryPort Protocol DI (reuses compliance_kb collection)
Trust Zone: GREEN
Autonomy: L2 — auto-resolves FAQs, escalates edge cases to human
"""

from __future__ import annotations

import logging
import os

from services.support.support_models import (
    AuditPort,
    FAQAnswer,
    InMemoryAuditPort,
    InMemoryKBPort,
    InMemoryTicketStore,
    KBQueryPort,
    SupportTicket,
    TicketStatus,
    TicketStorePort,
)

logger = logging.getLogger(__name__)

# Confidence threshold — above this the bot auto-resolves the ticket
_threshold_env = os.environ.get("SUPPORT_AUTO_RESOLVE_THRESHOLD", "0.80")
AUTO_RESOLVE_THRESHOLD = float(_threshold_env)  # nosemgrep: banxe-float-money

# Max KB results to inspect before forming answer
KB_TOP_K = int(os.environ.get("SUPPORT_KB_TOP_K", "3"))

# FAQ KB collection name
FAQ_COLLECTION = os.environ.get("SUPPORT_FAQ_COLLECTION", "banxe_faq")


class CustomerSupportAgent:
    """
    FAQ bot using RAG from compliance_kb.

    Flow:
      1. Query KB with ticket subject + body
      2. If top result confidence ≥ threshold → auto-resolve + close ticket
      3. Else → leave ticket open for human agent

    Trust Zone: GREEN
    Autonomy: L2 (auto-resolves FAQ, alerts for escalation)
    """

    def __init__(
        self,
        kb: KBQueryPort | None = None,
        ticket_store: TicketStorePort | None = None,
        audit: AuditPort | None = None,
    ) -> None:
        self._kb: KBQueryPort = kb or InMemoryKBPort()
        self._store: TicketStorePort = ticket_store or InMemoryTicketStore()
        self._audit: AuditPort = audit or InMemoryAuditPort()

    async def handle(self, ticket: SupportTicket) -> FAQAnswer:
        """
        Query KB and decide whether to auto-resolve or escalate.

        Returns FAQAnswer with auto_resolved=True if the bot closed the ticket,
        or auto_resolved=False if it should be routed to a human agent.
        """
        query_text = f"{ticket.subject}\n{ticket.body}"
        results = await self._kb.query(query_text, collection=FAQ_COLLECTION)

        if not results:
            await self._escalate_to_human(ticket, "No KB results found")
            return FAQAnswer(
                ticket_id=ticket.id,
                answer="I'm connecting you with a support specialist.",
                citations=[],
                confidence=0.0,
                auto_resolved=False,
            )

        top = results[0]
        answer_text: str = top.get("text", "")
        confidence: float = float(top.get("score", 0.0))  # nosemgrep: banxe-float-money
        citations: list[str] = [r.get("source", "") for r in results[:KB_TOP_K] if r.get("source")]

        auto_resolved = confidence >= AUTO_RESOLVE_THRESHOLD

        if auto_resolved:
            await self._store.update_status(
                ticket.id,
                TicketStatus.RESOLVED,
                resolution_summary=f"Auto-resolved by FAQ bot (confidence={confidence:.2f})",
            )
            await self._audit.log(
                "support.ticket_auto_resolved",
                {
                    "ticket_id": ticket.id,
                    "customer_id": ticket.customer_id,
                    "confidence": confidence,
                    "answer_preview": answer_text[:100],
                    "citations": citations,
                },
            )
            logger.info(
                "Ticket %s auto-resolved confidence=%.2f",
                ticket.id,
                confidence,
            )
        else:
            await self._escalate_to_human(
                ticket,
                f"KB confidence too low ({confidence:.2f} < {AUTO_RESOLVE_THRESHOLD})",
            )

        return FAQAnswer(
            ticket_id=ticket.id,
            answer=answer_text,
            citations=citations,
            confidence=confidence,
            auto_resolved=auto_resolved,
        )

    async def _escalate_to_human(self, ticket: SupportTicket, reason: str) -> None:
        await self._store.update_status(ticket.id, TicketStatus.IN_PROGRESS)
        await self._audit.log(
            "support.faq_escalated_to_human",
            {
                "ticket_id": ticket.id,
                "customer_id": ticket.customer_id,
                "reason": reason,
            },
        )
        logger.info("Ticket %s → human agent: %s", ticket.id, reason)
