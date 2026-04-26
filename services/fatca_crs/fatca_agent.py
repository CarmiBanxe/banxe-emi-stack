"""
services/fatca_crs/fatca_agent.py
FATCA/CRS agent orchestration (IL-FAT-01).
I-27: US person classification changes require COMPLIANCE_OFFICER (L4).
I-27: CRS classification overrides require MLRO (L4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib

from services.fatca_crs.fatca_models import CRSClassification


@dataclass
class FATCAHITLProposal:
    proposal_id: str
    cert_id: str
    action: str
    reason: str
    requires_approval_from: str
    approved: bool = False
    proposed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class FATCAAgent:
    """FATCA/CRS agent.

    L4 HITL: US person changes → COMPLIANCE_OFFICER.
    L4 HITL: CRS classification override → MLRO.
    """

    def __init__(self) -> None:
        self._proposals: list[FATCAHITLProposal] = []

    def propose_us_person_change(self, cert_id: str, new_value: bool) -> FATCAHITLProposal:
        pid = f"FPROP_{hashlib.sha256(cert_id.encode()).hexdigest()[:8]}"
        proposal = FATCAHITLProposal(
            proposal_id=pid,
            cert_id=cert_id,
            action=f"change_us_person_to_{new_value}",
            reason="US person indicator change requires compliance review",
            requires_approval_from="COMPLIANCE_OFFICER",
        )
        self._proposals.append(proposal)
        return proposal

    def propose_crs_override(
        self, cert_id: str, new_classification: CRSClassification
    ) -> FATCAHITLProposal:
        pid = f"FPROP_{hashlib.sha256(f'{cert_id}crs'.encode()).hexdigest()[:8]}"
        proposal = FATCAHITLProposal(
            proposal_id=pid,
            cert_id=cert_id,
            action=f"override_crs_classification_to_{new_classification.value}",
            reason="CRS classification override requires MLRO approval",
            requires_approval_from="MLRO",
        )
        self._proposals.append(proposal)
        return proposal

    @property
    def proposals(self) -> list[FATCAHITLProposal]:
        return list(self._proposals)
