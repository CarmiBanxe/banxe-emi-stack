"""
services/complaints/complaints_agent.py
FCA DISP complaints agent (IL-DSP-01).
I-27: redress > £500 requires COMPLAINTS_OFFICER (L4).
I-27: FOS escalation requires COMPLAINTS_OFFICER (L4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
import hashlib

from services.complaints.complaints_engine import REDRESS_HITL_THRESHOLD, ComplaintsEngine
from services.complaints.complaints_models import Resolution


@dataclass
class ComplaintsHITLProposal:
    proposal_id: str
    complaint_id: str
    action: str
    reason: str
    requires_approval_from: str = "COMPLAINTS_OFFICER"
    approved: bool = False
    proposed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class ComplaintsAgent:
    """Complaints management agent.

    L4 HITL: redress > £500 → COMPLAINTS_OFFICER.
    L4 HITL: FOS escalation → COMPLAINTS_OFFICER.
    """

    def __init__(self, engine: ComplaintsEngine | None = None) -> None:
        self._engine = engine or ComplaintsEngine()
        self._proposals: list[ComplaintsHITLProposal] = []

    def resolve_with_redress(
        self, complaint_id: str, outcome: str, redress_amount: str
    ) -> Resolution | ComplaintsHITLProposal:
        """Resolve complaint. I-27: redress > £500 requires COMPLAINTS_OFFICER."""
        amount = Decimal(redress_amount)
        if amount > REDRESS_HITL_THRESHOLD:
            pid = f"CPROP_{hashlib.sha256(complaint_id.encode()).hexdigest()[:8]}"
            proposal = ComplaintsHITLProposal(
                proposal_id=pid,
                complaint_id=complaint_id,
                action=f"resolve_with_redress_{redress_amount}",
                reason=f"Redress {redress_amount} > £{REDRESS_HITL_THRESHOLD} threshold (I-27)",
                requires_approval_from="COMPLAINTS_OFFICER",
            )
            self._proposals.append(proposal)
            return proposal
        return self._engine.resolve(complaint_id, outcome, redress_amount)

    @property
    def proposals(self) -> list[ComplaintsHITLProposal]:
        return list(self._proposals)
