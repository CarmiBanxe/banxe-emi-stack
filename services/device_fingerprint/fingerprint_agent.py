"""
services/device_fingerprint/fingerprint_agent.py
Device fingerprint agent (IL-DFP-01).
I-27: suspicious device requires FRAUD_ANALYST HITL (L4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
import hashlib

from services.device_fingerprint.fingerprint_engine import FingerprintEngine
from services.device_fingerprint.fingerprint_models import FingerprintData, MatchResult


@dataclass
class DeviceHITLProposal:
    proposal_id: str
    customer_id: str
    match_type: str
    risk_score: str
    requires_approval_from: str = "FRAUD_ANALYST"
    approved: bool = False
    proposed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class FingerprintAgent:
    """Device fingerprint agent.

    L4 HITL: suspicious device match requires FRAUD_ANALYST.
    """

    HITL_SCORE_THRESHOLD = Decimal("0.7")

    def __init__(self, engine: FingerprintEngine | None = None) -> None:
        self._engine = engine or FingerprintEngine()
        self._proposals: list[DeviceHITLProposal] = []

    def assess_device(
        self, customer_id: str, data: FingerprintData
    ) -> MatchResult | DeviceHITLProposal:
        result = self._engine.match_device(customer_id, data)
        if Decimal(result.risk_score) >= self.HITL_SCORE_THRESHOLD:
            pid = f"DPROP_{hashlib.sha256(f'{customer_id}{result.risk_score}'.encode()).hexdigest()[:8]}"
            proposal = DeviceHITLProposal(
                proposal_id=pid,
                customer_id=customer_id,
                match_type=result.match_type,
                risk_score=result.risk_score,
            )
            self._proposals.append(proposal)
            return proposal
        return result

    @property
    def proposals(self) -> list[DeviceHITLProposal]:
        return list(self._proposals)
