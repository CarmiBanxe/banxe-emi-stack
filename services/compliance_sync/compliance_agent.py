"""
services/compliance_sync/compliance_agent.py
Compliance Matrix agent orchestration (IL-CMS-01).
I-27: status change notifications require COMPLIANCE_OFFICER (L4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib

from services.compliance_sync.matrix_models import ArtifactStatus, ComplianceMatrixReport
from services.compliance_sync.matrix_scanner import MatrixScanner


@dataclass
class ComplianceSyncProposal:
    """I-27: proposal for compliance officer, not auto-applied."""

    proposal_id: str
    item_id: str
    old_status: ArtifactStatus
    new_status: ArtifactStatus
    requires_approval_from: str = "COMPLIANCE_OFFICER"
    approved: bool = False
    proposed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class ComplianceMatrixAgent:
    """Agent for compliance matrix sync.

    Autonomy: L4 — status changes require COMPLIANCE_OFFICER approval (I-27).
    """

    def __init__(self, scanner: MatrixScanner | None = None) -> None:
        self._scanner = scanner or MatrixScanner()
        self._proposals: list[ComplianceSyncProposal] = []  # I-24

    def run_scan(self) -> ComplianceMatrixReport:
        """Run a compliance scan and generate proposals for NOT_STARTED gaps."""
        report = self._scanner.scan_all()
        for entry in report.entries:
            if entry.status == ArtifactStatus.NOT_STARTED:
                pid = f"PROP_{hashlib.sha256(entry.item_id.encode()).hexdigest()[:8]}"
                self._proposals.append(
                    ComplianceSyncProposal(
                        proposal_id=pid,
                        item_id=entry.item_id,
                        old_status=ArtifactStatus.NOT_STARTED,
                        new_status=ArtifactStatus.DONE,
                        requires_approval_from="COMPLIANCE_OFFICER",
                    )
                )
        return report

    @property
    def proposals(self) -> list[ComplianceSyncProposal]:
        return list(self._proposals)
