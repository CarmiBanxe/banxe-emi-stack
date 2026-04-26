"""
services/complaints/complaints_engine.py
FCA DISP complaint lifecycle engine (IL-DSP-01).
SLA: 15 days simple, 35 days complex, 56 days final response.
I-01: redress amounts as Decimal.
I-24: ComplaintStore and AuditLog append-only.
BT-010: escalate_to_fos() raises NotImplementedError.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import hashlib
from typing import Protocol

from services.complaints.complaints_models import (
    Complaint,
    ComplaintCategory,
    ComplaintStatus,
    FOSEscalation,
    InvestigationReport,
    Resolution,
)

REDRESS_HITL_THRESHOLD = Decimal("500.00")  # I-27 threshold

# SLA days by category
_SLA_MAP = {
    ComplaintCategory.SERVICE_QUALITY: 15,
    ComplaintCategory.FEES_CHARGES: 15,
    ComplaintCategory.FRAUD_SCAM: 35,
    ComplaintCategory.PAYMENT_DELAY: 15,
    ComplaintCategory.ACCOUNT_ACCESS: 35,
    ComplaintCategory.DATA_PRIVACY: 35,
}


class ComplaintStorePort(Protocol):
    def save(self, complaint: Complaint) -> None: ...
    def get_by_id(self, complaint_id: str) -> Complaint | None: ...
    def list_all(self) -> list[Complaint]: ...


class InMemoryComplaintStore:
    def __init__(self) -> None:
        self._complaints: list[Complaint] = []  # I-24 append-only

    def save(self, complaint: Complaint) -> None:
        # Replace if exists (status update), else append
        for c in self._complaints:
            if c.complaint_id == complaint.complaint_id:
                # I-24: append new state, never delete old
                self._complaints.append(complaint)
                return
        self._complaints.append(complaint)

    def get_by_id(self, complaint_id: str) -> Complaint | None:
        # Return most recent entry for this complaint_id
        matches = [c for c in self._complaints if c.complaint_id == complaint_id]
        return matches[-1] if matches else None

    def list_all(self) -> list[Complaint]:
        # Return latest state for each complaint
        seen: dict[str, Complaint] = {}
        for c in self._complaints:
            seen[c.complaint_id] = c
        return list(seen.values())


class ComplaintsEngine:
    """FCA DISP complaint lifecycle engine.

    BT-010: escalate_to_fos() raises NotImplementedError (FOS portal → P1).
    """

    def __init__(self, store: ComplaintStorePort | None = None) -> None:
        self._store: ComplaintStorePort = store or InMemoryComplaintStore()
        self._audit_log: list[dict] = []  # I-24
        self._resolutions: list[Resolution] = []  # I-24

    def register(
        self, customer_id: str, category: ComplaintCategory, description: str
    ) -> Complaint:
        cid = f"cmp_{hashlib.sha256(f'{customer_id}{datetime.now(UTC).isoformat()}'.encode()).hexdigest()[:8]}"
        sla = _SLA_MAP.get(category, 15)
        complaint = Complaint(
            complaint_id=cid,
            customer_id=customer_id,
            category=category,
            description=description,
            status=ComplaintStatus.REGISTERED,
            registered_at=datetime.now(UTC).isoformat(),
            sla_days=sla,
        )
        self._store.save(complaint)
        self._audit_log.append({"event": "complaint.registered", "complaint_id": cid})
        return complaint

    def acknowledge(self, complaint_id: str) -> Complaint | None:
        complaint = self._store.get_by_id(complaint_id)
        if complaint is None:
            return None
        # Pydantic frozen — create new with updated status
        updated = complaint.model_copy(update={"status": ComplaintStatus.ACKNOWLEDGED})
        self._store.save(updated)
        self._audit_log.append({"event": "complaint.acknowledged", "complaint_id": complaint_id})
        return updated

    def investigate(
        self, complaint_id: str, investigator: str, findings: str
    ) -> InvestigationReport:
        complaint = self._store.get_by_id(complaint_id)
        if complaint:
            updated = complaint.model_copy(update={"status": ComplaintStatus.INVESTIGATING})
            self._store.save(updated)
        report = InvestigationReport(
            complaint_id=complaint_id,
            investigator=investigator,
            findings=findings,
            recommended_outcome="upheld",
            investigated_at=datetime.now(UTC).isoformat(),
        )
        self._audit_log.append({"event": "complaint.investigated", "complaint_id": complaint_id})
        return report

    def resolve(self, complaint_id: str, outcome: str, redress_amount: str = "0.00") -> Resolution:
        resolution = Resolution(
            complaint_id=complaint_id,
            outcome=outcome,
            redress_amount=redress_amount,
            resolved_at=datetime.now(UTC).isoformat(),
        )
        self._resolutions.append(resolution)  # I-24
        complaint = self._store.get_by_id(complaint_id)
        if complaint:
            updated = complaint.model_copy(update={"status": ComplaintStatus.RESOLVED})
            self._store.save(updated)
        self._audit_log.append(
            {
                "event": "complaint.resolved",
                "complaint_id": complaint_id,
                "outcome": outcome,
            }
        )
        return resolution

    def escalate_to_fos(self, complaint_id: str) -> FOSEscalation:
        """BT-010 stub: FOS portal integration requires P1 infrastructure."""
        raise NotImplementedError(
            "BT-010: FOS portal escalation not yet implemented. "
            "Requires FOS API integration (P1 item)."
        )

    def get_sla_approaching(self, warning_days: int = 5) -> list[Complaint]:
        """Return complaints approaching SLA deadline."""
        # In-memory stub: return all INVESTIGATING complaints as approaching
        all_complaints = self._store.list_all()
        return [
            c
            for c in all_complaints
            if c.status
            in (
                ComplaintStatus.REGISTERED,
                ComplaintStatus.ACKNOWLEDGED,
                ComplaintStatus.INVESTIGATING,
            )
        ]

    @property
    def audit_log(self) -> list[dict]:
        return list(self._audit_log)

    @property
    def resolutions(self) -> list[Resolution]:
        return list(self._resolutions)
