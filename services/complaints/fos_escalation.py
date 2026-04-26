"""
services/complaints/fos_escalation.py
Financial Ombudsman Service escalation (IL-FOS-01).
BT-010 completion: structured case preparation replacing NotImplementedError.
BT-011 stub: fos_portal_submit() raises NotImplementedError (FOS portal API -> P1).
I-24: FOSCaseLog append-only.
I-27: submit_case requires COMPLAINTS_OFFICER + HEAD_OF_COMPLIANCE (L4 dual sign-off).
8-week deadline: auto-flag at week 6 for FOS preparation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
from typing import Protocol

from services.complaints.fos_models import (
    CaseTimeline,
    CustomerStatement,
    FirmFinalResponse,
    FOSCasePackage,
    FOSCaseStatus,
    FOSSubmissionResult,
)

FOS_DEADLINE_WEEKS = 8
FOS_PREPARATION_TRIGGER_WEEKS = 6


class FOSCaseStorePort(Protocol):
    def save(self, package: FOSCasePackage) -> None: ...
    def get_by_id(self, case_id: str) -> FOSCasePackage | None: ...
    def list_all(self) -> list[FOSCasePackage]: ...


class InMemoryFOSCaseStore:
    def __init__(self) -> None:
        self._cases: list[FOSCasePackage] = []  # I-24 append-only

    def save(self, package: FOSCasePackage) -> None:
        self._cases.append(package)

    def get_by_id(self, case_id: str) -> FOSCasePackage | None:
        matches = [c for c in self._cases if c.case_id == case_id]
        return matches[-1] if matches else None

    def list_all(self) -> list[FOSCasePackage]:
        seen: dict[str, FOSCasePackage] = {}
        for c in self._cases:
            seen[c.case_id] = c
        return list(seen.values())


@dataclass
class FOSHITLProposal:
    """I-27: FOS submission requires dual sign-off (COMPLAINTS_OFFICER + HEAD_OF_COMPLIANCE)."""

    proposal_id: str
    case_id: str
    action: str
    requires_approval_from: list[str] = field(
        default_factory=lambda: ["COMPLAINTS_OFFICER", "HEAD_OF_COMPLIANCE"]
    )
    approved: bool = False
    proposed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class FOSEscalation:
    """FOS escalation case preparation and submission.

    BT-011: fos_portal_submit() raises NotImplementedError -- FOS portal API requires P1.
    I-24: case_log is append-only.
    I-27: submit_case requires dual sign-off.
    """

    def __init__(self, store: FOSCaseStorePort | None = None) -> None:
        self._store: FOSCaseStorePort = store or InMemoryFOSCaseStore()
        self._case_log: list[dict] = []  # I-24 append-only
        self._proposals: list[FOSHITLProposal] = []

    def prepare_case(
        self,
        complaint_id: str,
        customer_id: str,
        weeks_elapsed: int,
        complaint_events: list[dict] | None = None,
        firm_decision: str = "not_upheld",
        firm_reasoning: str = "No grounds found",
    ) -> FOSCasePackage:
        """Prepare a structured FOS case package from complaint data.

        Auto-flags case at week 6 (FOS_PREPARATION_TRIGGER_WEEKS).
        BT-010 completion: replaces the old NotImplementedError in escalate_to_fos().
        """
        case_id = (
            "fos_"
            + hashlib.sha256(f"{complaint_id}{datetime.now(UTC).isoformat()}".encode()).hexdigest()[
                :8
            ]
        )
        now = datetime.now(UTC).isoformat()
        events = complaint_events or [
            {"date": now, "description": "Complaint registered"},
            {"date": now, "description": "Firm final response issued"},
        ]
        timeline = CaseTimeline(
            complaint_id=complaint_id,
            events=events,
            weeks_elapsed=weeks_elapsed,
        )
        firm_response = FirmFinalResponse(
            complaint_id=complaint_id,
            decision=firm_decision,
            reasoning=firm_reasoning,
            issued_at=now,
        )
        customer_stmt = CustomerStatement(
            complaint_id=complaint_id,
            customer_id=customer_id,
            summary="Customer disputes firm's final response",
            desired_outcome="Full redress and apology",
        )
        status = (
            FOSCaseStatus.READY
            if weeks_elapsed >= FOS_PREPARATION_TRIGGER_WEEKS
            else FOSCaseStatus.PREPARING
        )
        package = FOSCasePackage(
            case_id=case_id,
            complaint_id=complaint_id,
            status=status,
            timeline=timeline,
            firm_final_response=firm_response,
            customer_statement=customer_stmt,
            prepared_at=now,
            weeks_since_complaint=weeks_elapsed,
        )
        self._store.save(package)
        self._case_log.append(
            {
                "event": "fos_case.prepared",
                "case_id": case_id,
                "complaint_id": complaint_id,
                "weeks_elapsed": weeks_elapsed,
                "logged_at": now,
            }
        )
        return package

    def submit_case(self, case_id: str) -> FOSSubmissionResult | FOSHITLProposal:
        """I-27: FOS submission always requires dual HITL sign-off."""
        pid = f"FOSHITL_{hashlib.sha256(case_id.encode()).hexdigest()[:8]}"
        proposal = FOSHITLProposal(
            proposal_id=pid,
            case_id=case_id,
            action="submit_fos_case",
        )
        self._proposals.append(proposal)
        return proposal

    def fos_portal_submit(self, case_package: FOSCasePackage) -> FOSSubmissionResult:
        """BT-011 stub: FOS portal API requires P1 infrastructure."""
        raise NotImplementedError(
            "BT-011: FOS portal API submission not yet implemented. "
            "Requires FOS API registration and credentials (P1 item)."
        )

    def get_week6_flagged(self) -> list[FOSCasePackage]:
        """Return cases at or past week 6 -- FOS preparation due."""
        return [
            c
            for c in self._store.list_all()
            if c.weeks_since_complaint >= FOS_PREPARATION_TRIGGER_WEEKS
            and c.status != FOSCaseStatus.SUBMITTED
        ]

    @property
    def case_log(self) -> list[dict]:
        return list(self._case_log)

    @property
    def proposals(self) -> list[FOSHITLProposal]:
        return list(self._proposals)
