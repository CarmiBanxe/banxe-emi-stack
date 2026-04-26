"""
services/customer_lifecycle/lifecycle_agent.py
Customer lifecycle agent (IL-LCY-01).
I-27: suspend requires COMPLIANCE_OFFICER (L4).
I-27: offboard requires HEAD_OF_COMPLIANCE (L4) -- data deletion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib

from services.customer_lifecycle.lifecycle_engine import LifecycleEngine


@dataclass
class LifecycleHITLProposal:
    proposal_id: str
    customer_id: str
    action: str
    reason: str
    requires_approval_from: str
    approved: bool = False
    proposed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class LifecycleAgent:
    """Customer lifecycle agent.

    L4 HITL: suspend -> COMPLIANCE_OFFICER.
    L4 HITL: offboard -> HEAD_OF_COMPLIANCE (data deletion under SYSC 9).
    """

    def __init__(self, engine: LifecycleEngine | None = None) -> None:
        self._engine = engine or LifecycleEngine()
        self._proposals: list[LifecycleHITLProposal] = []

    def propose_suspend(self, customer_id: str, reason: str) -> LifecycleHITLProposal:
        pid = f"LCPROP_{hashlib.sha256(f'{customer_id}suspend'.encode()).hexdigest()[:8]}"
        proposal = LifecycleHITLProposal(
            proposal_id=pid,
            customer_id=customer_id,
            action="suspend",
            reason=reason,
            requires_approval_from="COMPLIANCE_OFFICER",
        )
        self._proposals.append(proposal)
        return proposal

    def propose_offboard(self, customer_id: str, reason: str) -> LifecycleHITLProposal:
        pid = f"LCPROP_{hashlib.sha256(f'{customer_id}offboard'.encode()).hexdigest()[:8]}"
        proposal = LifecycleHITLProposal(
            proposal_id=pid,
            customer_id=customer_id,
            action="offboard",
            reason=reason,
            requires_approval_from="HEAD_OF_COMPLIANCE",
        )
        self._proposals.append(proposal)
        return proposal

    def propose_reactivate(self, customer_id: str, reason: str) -> LifecycleHITLProposal:
        pid = f"LCPROP_{hashlib.sha256(f'{customer_id}reactivate'.encode()).hexdigest()[:8]}"
        proposal = LifecycleHITLProposal(
            proposal_id=pid,
            customer_id=customer_id,
            action="reactivate",
            reason=reason,
            requires_approval_from="COMPLIANCE_OFFICER",
        )
        self._proposals.append(proposal)
        return proposal

    @property
    def proposals(self) -> list[LifecycleHITLProposal]:
        return list(self._proposals)
