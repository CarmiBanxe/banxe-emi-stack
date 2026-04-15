"""
services/support/ticket_routing_agent.py — Ticket Routing Agent
IL-CSB-01 | #109 | banxe-emi-stack

Routes inbound support tickets to the correct queue and assigns priority/SLA.

Categories (5):
  ACCOUNT  → account access, balance, card issues
  PAYMENT  → transfers, FPS, SEPA, FX
  KYC      → identity verification, document upload, limits
  FRAUD    → suspicious activity, disputed transactions
  GENERAL  → everything else

SLA contract (FCA DISP 1.3 — prompt handling):
  CRITICAL  → 1h   (confirmed fraud, safeguarding breach)
  HIGH      → 4h   (payment stuck, account locked)
  MEDIUM    → 24h  (KYC, general account questions)
  LOW       → 72h  (information requests, feedback)

Architecture: TicketRoutingPort Protocol DI
Trust Zone: GREEN (no PII in routing decision, no financial action)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
import re

from services.support.support_models import (
    SLA_HOURS,
    AuditPort,
    InMemoryAuditPort,
    InMemoryTicketStore,
    RoutingDecision,
    SupportTicket,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    TicketStorePort,
)

logger = logging.getLogger(__name__)


# ─── Keyword routing table ─────────────────────────────────────────────────────
# Patterns are case-insensitive. First match wins.

_CATEGORY_PATTERNS: list[tuple[TicketCategory, list[str]]] = [
    (
        TicketCategory.FRAUD,
        [
            r"\bfraud\b",
            r"\bscam\b",
            r"\bstolen\b",
            r"\bunauthori[sz]ed\b",
            r"\bdispute\b",
            r"\bchargeback\b",
            r"\bphish",
        ],
    ),
    (
        TicketCategory.PAYMENT,
        [
            r"\bpayment\b",
            r"\btransfer\b",
            r"\bfps\b",
            r"\bsepa\b",
            r"\btransaction\b",
            r"\bsent.*money\b",
            r"\bmoney.*sent\b",
            r"\bpending.*payment\b",
            r"\bfx\b",
            r"\bexchange\b",
        ],
    ),
    (
        TicketCategory.KYC,
        [
            r"\bkyc\b",
            r"\bverif",
            r"\bidentit",
            r"\bpassport\b",
            r"\blicense\b",
            r"\bdocument\b",
            r"\blimit\b",
            r"\brestricted\b",
        ],
    ),
    (
        TicketCategory.ACCOUNT,
        [
            r"\baccount\b",
            r"\bcard\b",
            r"\bpin\b",
            r"\bpassword\b",
            r"\blogin\b",
            r"\baccess\b",
            r"\bbalance\b",
            r"\bstatement\b",
            r"\bclosed.*account\b",
        ],
    ),
]

_PRIORITY_ESCALATION: dict[TicketCategory, TicketPriority] = {
    TicketCategory.FRAUD: TicketPriority.CRITICAL,
    TicketCategory.PAYMENT: TicketPriority.HIGH,
    TicketCategory.KYC: TicketPriority.MEDIUM,
    TicketCategory.ACCOUNT: TicketPriority.MEDIUM,
    TicketCategory.GENERAL: TicketPriority.LOW,
}

_QUEUE_MAP: dict[TicketCategory, str] = {
    TicketCategory.FRAUD: "fraud-team",
    TicketCategory.PAYMENT: "payments-support",
    TicketCategory.KYC: "kyc-team",
    TicketCategory.ACCOUNT: "account-support",
    TicketCategory.GENERAL: "general-support",
}

# Low-confidence FAQ topics that can be auto-resolved
_AUTO_RESOLVABLE_KEYWORDS = [
    r"\bhow do i\b",
    r"\bwhere can i\b",
    r"\bwhat is\b",
    r"\bwhen will\b",
    r"\bfee\b",
    r"\bcharge\b",
    r"\binterest\b",
]


def _classify_text(text: str) -> tuple[TicketCategory, float]:
    """Classify ticket text into category with confidence score."""
    lower = text.lower()
    for category, patterns in _CATEGORY_PATTERNS:
        matches = sum(1 for p in patterns if re.search(p, lower))
        if matches > 0:
            confidence = min(0.6 + matches * 0.1, 0.95)
            return category, confidence
    return TicketCategory.GENERAL, 0.5


def _is_auto_resolvable(text: str) -> bool:
    """True if ticket looks like a general FAQ question."""
    lower = text.lower()
    return any(re.search(p, lower) for p in _AUTO_RESOLVABLE_KEYWORDS)


class TicketRoutingAgent:
    """
    Routes support tickets to the correct queue and SLA tier.

    Trust Zone: GREEN
    Autonomy: L1 (fully automated, no financial or personal decisions)
    """

    def __init__(
        self,
        ticket_store: TicketStorePort | None = None,
        audit: AuditPort | None = None,
    ) -> None:
        self._store: TicketStorePort = ticket_store or InMemoryTicketStore()
        self._audit: AuditPort = audit or InMemoryAuditPort()

    async def route(self, ticket: SupportTicket) -> RoutingDecision:
        """Classify ticket, assign priority/queue, persist to store."""
        text = f"{ticket.subject} {ticket.body}"
        category, confidence = _classify_text(text)
        priority = _PRIORITY_ESCALATION[category]
        assigned_to = _QUEUE_MAP[category]
        auto_resolvable = category == TicketCategory.GENERAL and _is_auto_resolvable(text)

        # Mutate ticket with routing decision — recalculate SLA based on routed priority
        ticket.category = category
        ticket.priority = priority
        ticket.assigned_to = assigned_to
        ticket.status = TicketStatus.IN_PROGRESS
        sla_hours = SLA_HOURS[priority]
        ticket.sla_deadline = datetime.now(UTC) + timedelta(hours=sla_hours)

        await self._store.save(ticket)
        await self._audit.log(
            "support.ticket_routed",
            {
                "ticket_id": ticket.id,
                "customer_id": ticket.customer_id,
                "category": category.value,
                "priority": priority.value,
                "assigned_to": assigned_to,
                "confidence": confidence,
                "auto_resolvable": auto_resolvable,
                "channel": ticket.channel,
            },
        )

        logger.info(
            "Ticket %s routed → %s [%s] confidence=%.2f",
            ticket.id,
            assigned_to,
            priority.value,
            confidence,
        )

        return RoutingDecision(
            ticket_id=ticket.id,
            category=category,
            priority=priority,
            assigned_to=assigned_to,
            auto_resolvable=auto_resolvable,
            confidence=confidence,
        )
