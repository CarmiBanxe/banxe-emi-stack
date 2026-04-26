"""
services/ato_prevention/ato_agent.py
ATO Prevention agent (IL-ATO-01).
I-27: account lockout requires SECURITY_OFFICER HITL (L4).
I-27: unlock requires SECURITY_OFFICER HITL (L4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
import hashlib

from services.ato_prevention.ato_engine import ATOEngine
from services.ato_prevention.ato_models import ATOAssessment, LoginAttempt


@dataclass
class ATOHITLProposal:
    proposal_id: str
    customer_id: str
    action: str
    risk_score: str
    reason: str
    requires_approval_from: str = "SECURITY_OFFICER"
    approved: bool = False
    proposed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class ATOAgent:
    """ATO prevention agent.

    L4 HITL: lockout and unlock both require SECURITY_OFFICER.
    """

    LOCK_THRESHOLD = Decimal("0.8")

    def __init__(self, engine: ATOEngine | None = None) -> None:
        self._engine = engine or ATOEngine()
        self._proposals: list[ATOHITLProposal] = []
        self._locked_customers: set[str] = set()

    def assess_and_act(self, attempt: LoginAttempt) -> ATOAssessment | ATOHITLProposal:
        assessment = self._engine.assess_login(attempt)
        if Decimal(assessment.risk_score) >= self.LOCK_THRESHOLD:
            pid = f"ATOPROP_{hashlib.sha256(attempt.customer_id.encode()).hexdigest()[:8]}"
            proposal = ATOHITLProposal(
                proposal_id=pid,
                customer_id=attempt.customer_id,
                action="lock_account",
                risk_score=assessment.risk_score,
                reason=f"ATO score {assessment.risk_score} >= lock threshold. Signals: {assessment.signals}",
            )
            self._proposals.append(proposal)
            return proposal
        return assessment

    def propose_unlock(self, customer_id: str, officer: str) -> ATOHITLProposal:
        """I-27: unlock requires SECURITY_OFFICER."""
        pid = f"UNLOCK_{hashlib.sha256(f'{customer_id}unlock'.encode()).hexdigest()[:8]}"
        proposal = ATOHITLProposal(
            proposal_id=pid,
            customer_id=customer_id,
            action="unlock_account",
            risk_score="0.0",
            reason=f"Unlock requested by {officer}",
        )
        self._proposals.append(proposal)
        return proposal

    @property
    def proposals(self) -> list[ATOHITLProposal]:
        return list(self._proposals)
