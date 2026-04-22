"""
services/fraud_tracer/tracer_agent.py
Fraud Tracer agent orchestration (IL-TRC-01).
I-27: fraud score > 0.8 requires FRAUD_ANALYST approval (L4 HITL).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
import hashlib

from services.fraud_tracer.tracer_engine import TracerEngine
from services.fraud_tracer.tracer_models import TraceRequest, TraceResult


@dataclass
class FraudHITLProposal:
    """I-27: high-score transaction requiring FRAUD_ANALYST review."""

    proposal_id: str
    transaction_id: str
    score: str  # Decimal as string
    flags: list[str]
    requires_approval_from: str = "FRAUD_ANALYST"
    approved: bool = False
    proposed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class FraudTracerAgent:
    """Fraud Tracer agent.

    L4 HITL: transactions with fraud score > 0.8 require FRAUD_ANALYST.
    """

    HITL_THRESHOLD = Decimal("0.8")

    def __init__(self, engine: TracerEngine | None = None) -> None:
        self._engine = engine or TracerEngine()
        self._proposals: list[FraudHITLProposal] = []

    def trace_and_decide(self, request: TraceRequest) -> TraceResult | FraudHITLProposal:
        result = self._engine.trace(request)
        if Decimal(result.score) >= self.HITL_THRESHOLD:
            pid = f"FPROP_{hashlib.sha256(request.transaction_id.encode()).hexdigest()[:8]}"
            proposal = FraudHITLProposal(
                proposal_id=pid,
                transaction_id=request.transaction_id,
                score=result.score,
                flags=result.flags,
            )
            self._proposals.append(proposal)
            return proposal
        return result

    @property
    def proposals(self) -> list[FraudHITLProposal]:
        return list(self._proposals)
