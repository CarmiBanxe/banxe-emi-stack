"""
complaint_service.py — FCA Consumer Duty / DISP Complaints Service
IL-022 | FCA Consumer Duty DISP 1.4 (8-week SLA) | banxe-emi-stack

WHY THIS EXISTS
---------------
FCA Consumer Duty (PS22/9) requires firms to resolve complaints within 8 weeks
(56 days). At week 7, a warning must be sent. If unresolved at week 8, the firm
must notify the customer of their right to escalate to FOS (Financial Ombudsman
Service). Audit trail of all state transitions is mandatory (DISP 1.10).

Architecture: IL-022, ClickHouse complaints + complaint_events tables
CTX-03 AMBER — writes to ClickHouse, triggers n8n webhook
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Protocol

import httpx

logger = logging.getLogger(__name__)

# FCA DISP 1.4.1R — 8 weeks = 56 calendar days
SLA_DAYS = int(os.environ.get("COMPLAINT_SLA_DAYS", "56"))
# Warning at 7 days before deadline
SLA_WARNING_DAYS = int(os.environ.get("COMPLAINT_SLA_WARNING_DAYS", "7"))

N8N_WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL", "")
TELEGRAM_MLRO_CHAT_ID = os.environ.get("TELEGRAM_MLRO_CHAT_ID", "")


# ─── Data classes ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Complaint:
    id: str
    customer_id: str
    category: str
    description: str
    status: str
    created_at: datetime
    sla_deadline: datetime
    resolved_at: Optional[datetime]
    resolution_summary: str
    assigned_to: str


@dataclass(frozen=True)
class SLABreach:
    """A complaint that has exceeded its 8-week SLA."""
    complaint_id: str
    customer_id: str
    category: str
    created_at: datetime
    sla_deadline: datetime
    days_overdue: int


@dataclass(frozen=True)
class SLAWarning:
    """A complaint approaching its SLA deadline (within 7 days)."""
    complaint_id: str
    customer_id: str
    sla_deadline: datetime
    days_remaining: int


# ─── Protocol (testable without ClickHouse) ───────────────────────────────────

class ComplaintRepository(Protocol):
    def insert_complaint(self, complaint_id: str, customer_id: str,
                         category: str, description: str,
                         sla_deadline: datetime, channel: str,
                         created_by: str) -> None: ...

    def update_status(self, complaint_id: str, new_status: str,
                      resolved_at: Optional[datetime],
                      resolution_summary: str) -> None: ...

    def insert_event(self, complaint_id: str, event_type: str,
                     old_status: str, new_status: str,
                     note: str, actor: str) -> None: ...

    def get_sla_breaches(self) -> List[dict]: ...

    def get_sla_warnings(self) -> List[dict]: ...

    def get_complaint(self, complaint_id: str) -> Optional[dict]: ...


# ─── ClickHouse implementation ────────────────────────────────────────────────

class ClickHouseComplaintRepository:  # pragma: no cover
    """
    Production repository — writes to banxe.complaints and banxe.complaint_events.

    Tables created by: scripts/schema/clickhouse_complaints.sql
    """

    def __init__(self, ch_client):
        self._ch = ch_client

    def insert_complaint(self, complaint_id: str, customer_id: str,
                         category: str, description: str,
                         sla_deadline: datetime, channel: str = "API",
                         created_by: str = "system") -> None:
        self._ch.execute(
            """
            INSERT INTO banxe.complaints
              (id, customer_id, category, description, status,
               created_at, sla_deadline, channel, created_by)
            VALUES
            """,
            [{
                "id": complaint_id,
                "customer_id": customer_id,
                "category": category,
                "description": description,
                "status": "OPEN",
                "created_at": datetime.now(timezone.utc),
                "sla_deadline": sla_deadline,
                "channel": channel,
                "created_by": created_by,
            }]
        )

    def update_status(self, complaint_id: str, new_status: str,
                      resolved_at: Optional[datetime] = None,
                      resolution_summary: str = "") -> None:
        # ClickHouse: UPDATE via ALTER TABLE UPDATE (MergeTree mutation)
        set_clause = f"status = '{new_status}'"
        if resolution_summary:
            set_clause += f", resolution_summary = '{resolution_summary}'"
        if resolved_at:
            ts = resolved_at.strftime("%Y-%m-%d %H:%M:%S")
            set_clause += f", resolved_at = '{ts}'"
        self._ch.execute(
            f"ALTER TABLE banxe.complaints UPDATE {set_clause} "
            f"WHERE id = '{complaint_id}'"
        )

    def insert_event(self, complaint_id: str, event_type: str,
                     old_status: str = "", new_status: str = "",
                     note: str = "", actor: str = "system") -> None:
        self._ch.execute(
            """
            INSERT INTO banxe.complaint_events
              (complaint_id, event_type, old_status, new_status, note, actor)
            VALUES
            """,
            [{
                "complaint_id": complaint_id,
                "event_type": event_type,
                "old_status": old_status,
                "new_status": new_status,
                "note": note,
                "actor": actor,
            }]
        )

    def get_sla_breaches(self) -> List[dict]:
        rows = self._ch.execute(
            """
            SELECT id, customer_id, category, created_at, sla_deadline,
                   dateDiff('day', sla_deadline, now()) AS days_overdue
            FROM banxe.complaints
            WHERE status NOT IN ('RESOLVED', 'FOS_ESCALATED')
              AND sla_deadline < now()
            ORDER BY sla_deadline ASC
            """
        )
        return [
            {
                "complaint_id": str(r[0]), "customer_id": r[1],
                "category": r[2], "created_at": r[3],
                "sla_deadline": r[4], "days_overdue": r[5],
            }
            for r in rows
        ]

    def get_sla_warnings(self) -> List[dict]:
        warning_cutoff = datetime.now(timezone.utc) + timedelta(days=SLA_WARNING_DAYS)
        rows = self._ch.execute(
            """
            SELECT id, customer_id, category, created_at, sla_deadline,
                   dateDiff('day', now(), sla_deadline) AS days_remaining
            FROM banxe.complaints
            WHERE status NOT IN ('RESOLVED', 'FOS_ESCALATED')
              AND sla_deadline >= now()
              AND sla_deadline <= %(cutoff)s
            ORDER BY sla_deadline ASC
            """,
            {"cutoff": warning_cutoff}
        )
        return [
            {
                "complaint_id": str(r[0]), "customer_id": r[1],
                "category": r[2], "created_at": r[3],
                "sla_deadline": r[4], "days_remaining": r[5],
            }
            for r in rows
        ]

    def get_complaint(self, complaint_id: str) -> Optional[dict]:
        rows = self._ch.execute(
            "SELECT id, customer_id, category, description, status, "
            "created_at, sla_deadline, resolved_at, resolution_summary, assigned_to "
            "FROM banxe.complaints WHERE id = %(id)s LIMIT 1",
            {"id": complaint_id}
        )
        if not rows:
            return None
        r = rows[0]
        return {
            "id": str(r[0]), "customer_id": r[1], "category": r[2],
            "description": r[3], "status": r[4], "created_at": r[5],
            "sla_deadline": r[6], "resolved_at": r[7],
            "resolution_summary": r[8], "assigned_to": r[9],
        }


# ─── ComplaintService ─────────────────────────────────────────────────────────

class ComplaintService:
    """
    FCA Consumer Duty / DISP complaints lifecycle manager.

    FCA rule: DISP 1.4.1R — respond within 8 weeks.
    FCA rule: DISP 1.10.1R — maintain audit record of all complaints.
    """

    def __init__(self, repo: ComplaintRepository):
        self._repo = repo

    def open_complaint(self, customer_id: str, category: str,
                       description: str, channel: str = "API",
                       created_by: str = "system") -> str:
        """
        Create a new complaint. Returns complaint_id (UUID string).
        Automatically sets SLA deadline to +56 days (DISP 1.4.1R).
        Appends OPENED event to audit trail.
        """
        complaint_id = str(uuid.uuid4())
        sla_deadline = datetime.now(timezone.utc) + timedelta(days=SLA_DAYS)

        self._repo.insert_complaint(
            complaint_id=complaint_id,
            customer_id=customer_id,
            category=category,
            description=description,
            sla_deadline=sla_deadline,
            channel=channel,
            created_by=created_by,
        )
        self._repo.insert_event(
            complaint_id=complaint_id,
            event_type="OPENED",
            note=f"Complaint received via {channel}. SLA deadline: {sla_deadline.date()}",
            actor=created_by,
        )
        logger.info("Complaint opened: id=%s customer=%s sla=%s",
                    complaint_id, customer_id, sla_deadline.date())
        _fire_n8n_alert("complaint_opened", {
            "complaint_id": complaint_id,
            "customer_id": customer_id,
            "category": category,
            "sla_deadline": sla_deadline.isoformat(),
        })
        return complaint_id

    def resolve_complaint(self, complaint_id: str, resolution_summary: str,
                          actor: str = "system") -> None:
        """
        Mark complaint as RESOLVED. Appends audit event.
        """
        resolved_at = datetime.now(timezone.utc)
        row = self._repo.get_complaint(complaint_id)
        old_status = row["status"] if row else "OPEN"

        self._repo.update_status(
            complaint_id=complaint_id,
            new_status="RESOLVED",
            resolved_at=resolved_at,
            resolution_summary=resolution_summary,
        )
        self._repo.insert_event(
            complaint_id=complaint_id,
            event_type="RESOLVED",
            old_status=old_status,
            new_status="RESOLVED",
            note=resolution_summary[:500],
            actor=actor,
        )
        logger.info("Complaint resolved: id=%s", complaint_id)

    def check_sla_breaches(self) -> List[SLABreach]:
        """
        Return all complaints past their 8-week SLA deadline.
        Called by n8n cron daily. Each breach fires an MLRO alert.
        """
        rows = self._repo.get_sla_breaches()
        breaches = [
            SLABreach(
                complaint_id=r["complaint_id"],
                customer_id=r["customer_id"],
                category=r["category"],
                created_at=r["created_at"],
                sla_deadline=r["sla_deadline"],
                days_overdue=r["days_overdue"],
            )
            for r in rows
        ]
        if breaches:
            logger.warning("SLA breaches detected: %d complaints overdue", len(breaches))
            for b in breaches:
                self._repo.insert_event(
                    complaint_id=b.complaint_id,
                    event_type="SLA_BREACHED",
                    note=f"SLA breached by {b.days_overdue} day(s). Auto-escalation to FOS pending.",
                    actor="system",
                )
        return breaches

    def check_sla_warnings(self) -> List[SLAWarning]:
        """
        Return complaints within SLA_WARNING_DAYS of their deadline.
        Called by n8n cron daily.
        """
        rows = self._repo.get_sla_warnings()
        warnings = [
            SLAWarning(
                complaint_id=r["complaint_id"],
                customer_id=r["customer_id"],
                sla_deadline=r["sla_deadline"],
                days_remaining=r["days_remaining"],
            )
            for r in rows
        ]
        if warnings:
            for w in warnings:
                self._repo.insert_event(
                    complaint_id=w.complaint_id,
                    event_type="SLA_WARNING",
                    note=f"SLA deadline in {w.days_remaining} day(s). Immediate resolution required.",
                    actor="system",
                )
        return warnings

    def escalate_to_fos(self, complaint_id: str, fos_reference: str = "",
                        actor: str = "system") -> None:
        """
        Escalate complaint to Financial Ombudsman Service.
        Sets status = FOS_ESCALATED. Customer must be notified of FOS right.
        FCA DISP 1.4.1R — if unresolved at 8 weeks, FOS escalation is mandatory.
        """
        row = self._repo.get_complaint(complaint_id)
        old_status = row["status"] if row else "OPEN"

        self._repo.update_status(
            complaint_id=complaint_id,
            new_status="FOS_ESCALATED",
            resolution_summary=f"Escalated to FOS. Reference: {fos_reference}",
        )
        self._repo.insert_event(
            complaint_id=complaint_id,
            event_type="FOS_ESCALATED",
            old_status=old_status,
            new_status="FOS_ESCALATED",
            note=f"FOS escalation triggered. Ref: {fos_reference or 'pending'}",
            actor=actor,
        )
        _fire_n8n_alert("fos_escalation", {
            "complaint_id": complaint_id,
            "fos_reference": fos_reference,
            "actor": actor,
        })
        logger.warning("Complaint escalated to FOS: id=%s ref=%s", complaint_id, fos_reference)


# ─── n8n alert helper ─────────────────────────────────────────────────────────

def _fire_n8n_alert(event_type: str, payload: dict) -> None:
    """Fire n8n webhook. Non-blocking — failure is logged, never raised."""
    if not N8N_WEBHOOK_URL:
        return
    try:
        httpx.post(
            N8N_WEBHOOK_URL,
            json={"event": event_type, "source": "complaint_service", **payload},
            timeout=5.0,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("n8n alert failed (non-fatal): %s", exc)
