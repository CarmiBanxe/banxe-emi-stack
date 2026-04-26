"""
services/client_statements/statement_agent.py
Client statement agent orchestration (IL-CST-01).
I-27: manual statement correction requires OPERATIONS_OFFICER (L4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib

from services.client_statements.statement_generator import StatementGenerator


@dataclass
class StatementHITLProposal:
    proposal_id: str
    statement_id: str
    action: str
    reason: str
    requires_approval_from: str = "OPERATIONS_OFFICER"
    approved: bool = False
    proposed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class StatementAgent:
    """Statement agent.

    L4 HITL: manual corrections require OPERATIONS_OFFICER.
    """

    def __init__(self, generator: StatementGenerator | None = None) -> None:
        self._generator = generator or StatementGenerator()
        self._proposals: list[StatementHITLProposal] = []

    def propose_correction(self, statement_id: str, reason: str) -> StatementHITLProposal:
        pid = f"SPROP_{hashlib.sha256(statement_id.encode()).hexdigest()[:8]}"
        proposal = StatementHITLProposal(
            proposal_id=pid,
            statement_id=statement_id,
            action="manual_correction",
            reason=reason,
        )
        self._proposals.append(proposal)
        return proposal

    @property
    def proposals(self) -> list[StatementHITLProposal]:
        return list(self._proposals)
