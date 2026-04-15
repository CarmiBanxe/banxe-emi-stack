"""
services/support/complaint_triage_agent.py — Complaint Triage Agent
IL-CSB-01 | #112 | banxe-emi-stack

Links inbound complaints to the FCA DISP workflow (complaint_service IL-022).
Determines if a support ticket constitutes a formal FCA complaint and routes
it to the regulated complaint handling process.

FCA DISP 1.6: firms must have an effective complaint-handling process.
FCA DISP 1.3: complaints must be acknowledged within 5 business days.

Triage logic:
  A ticket is a formal DISP complaint if it contains:
  - An expression of dissatisfaction (explicit keyword OR high sentiment)
  - A reference to financial harm, service failure, or regulatory rights
  - The customer has not already received a satisfactory resolution

Architecture: TicketStorePort + AuditPort + N8NWebhookPort Protocol DI
Links to: services/complaints/complaint_service.py (IL-022)
Trust Zone: AMBER (DISP complaint data is sensitive)
Autonomy: L2 — auto-classifies, human MLRO/complaint handler decides action
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import re

from services.support.support_models import (
    AuditPort,
    EscalationReason,
    InMemoryAuditPort,
    InMemoryN8NPort,
    InMemoryTicketStore,
    N8NWebhookPort,
    SupportTicket,
    TicketStatus,
    TicketStorePort,
)

logger = logging.getLogger(__name__)

# DISP triage keywords (FCA DISP 1.1 — definition of complaint)
_DISSATISFACTION_PATTERNS = [
    r"\bcomplaint\b",
    r"\bdissatisfied\b",
    r"\bunhappy\b",
    r"\bupset\b",
    r"\bangry\b",
    r"\bdisappointed\b",
    r"\bnot acceptable\b",
    r"\bunacceptable\b",
    r"\boutraged\b",
    r"\bpoor service\b",
    r"\bterrible\b",
]

_FINANCIAL_HARM_PATTERNS = [
    r"\blose money\b",
    r"\blost money\b",
    r"\bfinancial loss\b",
    r"\bcharged incorrectly\b",
    r"\bovercharged\b",
    r"\bfees\b",
    r"\brefund\b",
    r"\bcompensation\b",
    r"\bwrong amount\b",
]

_REGULATORY_RIGHTS_PATTERNS = [
    r"\bfca\b",
    r"\bfinancial ombudsman\b",
    r"\bfos\b",
    r"\bregulator\b",
    r"\bright to complain\b",
    r"\bdisp\b",
    r"\bconsumer duty\b",
]

N8N_COMPLAINT_EVENT = "support.formal_complaint_triaged"


@dataclass(frozen=True)
class TriageResult:
    ticket_id: str
    is_formal_complaint: bool
    confidence: float
    complaint_id: str | None  # IL-022 complaint ID if created
    disp_category: str
    triage_reason: str


class ComplaintTriageAgent:
    """
    Classifies tickets as formal DISP complaints and routes them.

    When a ticket is classified as a formal complaint:
      1. Marks ticket status as ESCALATED
      2. Triggers n8n webhook to create IL-022 complaint record
      3. Logs to audit trail (I-24, FCA DISP 1.10)

    Trust Zone: AMBER
    Autonomy: L2 (classifies automatically, human handles the complaint)
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

    async def triage(self, ticket: SupportTicket) -> TriageResult:
        """
        Triage a support ticket against FCA DISP 1.1 complaint definition.

        FCA DISP 1.1.2R: a complaint is any oral or written expression of
        dissatisfaction from an eligible complainant about a regulated activity.
        """
        text = f"{ticket.subject} {ticket.body}".lower()
        is_complaint, confidence, disp_category, reason = self._classify(text)

        complaint_id: str | None = None

        if is_complaint:
            # Escalate ticket to DISP workflow
            await self._store.update_status(
                ticket.id,
                TicketStatus.ESCALATED,
            )
            ticket.escalation_reason = EscalationReason.COMPLAINT_REGULATORY

            # Trigger n8n to create IL-022 complaint record
            webhook_payload = {
                "ticket_id": ticket.id,
                "customer_id": ticket.customer_id,
                "subject": ticket.subject,
                "body": ticket.body,
                "disp_category": disp_category,
                "channel": ticket.channel,
                "confidence": confidence,
            }
            await self._n8n.trigger(N8N_COMPLAINT_EVENT, webhook_payload)

            await self._audit.log(
                "support.formal_complaint_created",
                {
                    "ticket_id": ticket.id,
                    "customer_id": ticket.customer_id,
                    "disp_category": disp_category,
                    "confidence": confidence,
                    "reason": reason,
                    "regulation": "FCA DISP 1.1",
                },
            )
            logger.warning(
                "DISP COMPLAINT: ticket=%s customer=%s disp_cat=%s conf=%.2f",
                ticket.id,
                ticket.customer_id,
                disp_category,
                confidence,
            )
        else:
            await self._audit.log(
                "support.complaint_triage_not_disp",
                {
                    "ticket_id": ticket.id,
                    "confidence": confidence,
                    "reason": reason,
                },
            )

        return TriageResult(
            ticket_id=ticket.id,
            is_formal_complaint=is_complaint,
            confidence=confidence,
            complaint_id=complaint_id,
            disp_category=disp_category,
            triage_reason=reason,
        )

    def _classify(self, text: str) -> tuple[bool, float, str, str]:
        """Classify text as formal complaint. Returns (is_complaint, confidence, category, reason)."""
        dissatisfied = any(re.search(p, text) for p in _DISSATISFACTION_PATTERNS)
        financial_harm = any(re.search(p, text) for p in _FINANCIAL_HARM_PATTERNS)
        regulatory = any(re.search(p, text) for p in _REGULATORY_RIGHTS_PATTERNS)

        match_count = sum([dissatisfied, financial_harm, regulatory])

        if regulatory:
            return True, 0.95, "REGULATORY_RIGHTS", "Customer cited regulatory rights"
        if dissatisfied and financial_harm:
            return True, 0.88, "FINANCIAL_DISSATISFACTION", "Dissatisfaction + financial harm"
        if dissatisfied:
            return True, 0.70, "SERVICE_DISSATISFACTION", "Expression of dissatisfaction"
        if financial_harm:
            return True, 0.65, "FINANCIAL_HARM", "Financial harm without explicit dissatisfaction"

        confidence = max(0.0, match_count * 0.15)
        return False, confidence, "NOT_DISP", f"No DISP indicators ({match_count} partial matches)"
