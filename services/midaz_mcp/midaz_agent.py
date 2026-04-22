"""
services/midaz_mcp/midaz_agent.py
Midaz MCP agent orchestration (IL-MCP-01).
I-27: transactions > £10,000 require COMPLIANCE_OFFICER (L4 HITL).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
import hashlib

from services.midaz_mcp.midaz_client import EDD_THRESHOLD, MidazClient
from services.midaz_mcp.midaz_models import Transaction, TransactionEntry

EDD_THRESHOLD_INDIVIDUAL = EDD_THRESHOLD  # £10,000


@dataclass
class MidazHITLProposal:
    """I-27: transaction requiring human approval."""

    proposal_id: str
    ledger_id: str
    total_amount: str  # Decimal as string
    reason: str
    requires_approval_from: str = "COMPLIANCE_OFFICER"
    approved: bool = False
    proposed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class MidazAgent:
    """Midaz CBS agent.

    L4 HITL: transactions with total debit > £10,000 require COMPLIANCE_OFFICER.
    """

    def __init__(self, client: MidazClient | None = None) -> None:
        self._client = client or MidazClient()
        self._proposals: list[MidazHITLProposal] = []

    async def submit_transaction(
        self, ledger_id: str, entries: list[TransactionEntry]
    ) -> Transaction | MidazHITLProposal:
        total = sum(Decimal(e.amount) for e in entries if e.direction == "DEBIT")
        if total >= EDD_THRESHOLD_INDIVIDUAL:
            pid = f"MPROP_{hashlib.sha256(ledger_id.encode()).hexdigest()[:8]}"
            proposal = MidazHITLProposal(
                proposal_id=pid,
                ledger_id=ledger_id,
                total_amount=str(total),
                reason=(
                    f"Total debit {total} >= EDD threshold {EDD_THRESHOLD_INDIVIDUAL} (I-04/I-27)"
                ),
            )
            self._proposals.append(proposal)
            return proposal
        return await self._client.create_transaction(ledger_id, entries)

    @property
    def proposals(self) -> list[MidazHITLProposal]:
        return list(self._proposals)
