"""
services/gabriel/returns_governor.py
ReturnsGovernor — K-gabriel orchestrator for FCA return submissions.

Responsibilities (K-gabriel spec §3):
  - Config-driven return schedule (FIN060 monthly, breach ad-hoc)
  - Deadline tracking: days remaining before FCA Gabriel cutoff
  - Idempotency: same (return_type, return_period) → same SubmissionRecord
  - Breach→draft: safeguarding.breach.detected → DRAFT SubmissionRecord (I-27)
  - Pre-submission validation gate: blocks invalid drafts from reaching HITL
  - Append-only audit trail for every state transition (I-24, I-08)

I-27: ReturnsGovernor NEVER calls GabrielSubmissionPort autonomously.
      Submission is reserved for an explicit human-approved action.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
import logging
from uuid import uuid4

from services.gabriel.gabriel_models import (
    DeadlineStatus,
    GabrielAuditEntry,
    GabrielAuditPort,
    GabrielReturnStatus,
    GabrielReturnType,
    InMemoryGabrielAuditPort,
    ReturnSchedule,
    SubmissionRecord,
)
from services.recon.breach_notify_port import BreachEvent

logger = logging.getLogger(__name__)

# ── Default config ────────────────────────────────────────────────────────────

_DEFAULT_SCHEDULE: dict[GabrielReturnType, ReturnSchedule] = {
    GabrielReturnType.FIN060: ReturnSchedule(
        return_type=GabrielReturnType.FIN060,
        frequency="MONTHLY",
        deadline_day=15,
        fca_item_code="FIN060-MONTHLY",
    ),
    GabrielReturnType.BREACH_REPORT: ReturnSchedule(
        return_type=GabrielReturnType.BREACH_REPORT,
        frequency="AD_HOC",
        deadline_day=2,  # 48h per PS23/3 §5
        fca_item_code="BREACH-SAFEGUARD",
    ),
}


# ── ReturnsGovernor ───────────────────────────────────────────────────────────


class ReturnsGovernor:
    """Orchestrates FCA Gabriel return lifecycle from draft to HITL.

    Args:
        audit: Append-only audit port (I-24). Defaults to InMemory.
        schedule_config: Override return schedule (useful for tests).
    """

    def __init__(
        self,
        audit: GabrielAuditPort | None = None,
        schedule_config: dict[GabrielReturnType, ReturnSchedule] | None = None,
    ) -> None:
        self._audit: GabrielAuditPort = audit or InMemoryGabrielAuditPort()
        self._schedule = schedule_config if schedule_config is not None else _DEFAULT_SCHEDULE
        self._records: dict[str, SubmissionRecord] = {}  # idempotency_key → record

    # ── Public: schedule access ───────────────────────────────────────────────

    def get_schedule(self, return_type: GabrielReturnType) -> ReturnSchedule:
        """Return the configured schedule for a return type."""
        if return_type not in self._schedule:
            raise KeyError(f"No schedule configured for {return_type}")
        return self._schedule[return_type]

    # ── Public: deadline tracking ──────────────────────────────────────────────

    def get_deadline_status(
        self, return_type: GabrielReturnType, return_period: str
    ) -> DeadlineStatus:
        """Compute days remaining before FCA Gabriel cutoff.

        For FIN060 "YYYY-MM": deadline = 15th of the following month.
        For BREACH_REPORT "YYYY-MM-DD": deadline = detected_date + 2 days.
        """
        schedule = self.get_schedule(return_type)
        today = date.today()

        if return_type == GabrielReturnType.FIN060:
            year, month = int(return_period[:4]), int(return_period[5:7])
            # Advance to next month
            if month == 12:
                deadline = date(year + 1, 1, schedule.deadline_day)
            else:
                deadline = date(year, month + 1, schedule.deadline_day)
        else:
            # Ad-hoc breach: deadline is period_date + deadline_day days
            period_date = date.fromisoformat(return_period)
            from datetime import timedelta

            deadline = period_date + timedelta(days=schedule.deadline_day)

        days_remaining = (deadline - today).days
        return DeadlineStatus(
            return_type=return_type,
            return_period=return_period,
            deadline_date=deadline.isoformat(),
            days_remaining=days_remaining,
            is_overdue=days_remaining < 0,
        )

    # ── Public: idempotent create ──────────────────────────────────────────────

    def get_or_create(
        self,
        return_type: GabrielReturnType,
        return_period: str,
        validated_by: str = "SYSTEM",
        source_recon_id: str | None = None,
    ) -> SubmissionRecord:
        """Return existing draft for (type, period) or create a new one.

        Idempotency: repeated calls with the same key return the same record
        without creating duplicates (K-gabriel spec §3.2).
        """
        ikey = f"{return_type.value}:{return_period}"
        if ikey in self._records:
            return self._records[ikey]

        schedule = self.get_schedule(return_type)
        record = SubmissionRecord(
            submission_id=str(uuid4()),
            return_type=return_type,
            return_period=return_period,
            fca_item_code=schedule.fca_item_code,
            prepared_at=datetime.now(UTC).isoformat(),
            validated_by=validated_by,
            status=GabrielReturnStatus.DRAFT,
            idempotency_key=ikey,
            source_recon_id=source_recon_id,
        )
        self._records[ikey] = record
        self._audit.record(
            GabrielAuditEntry(
                submission_id=record.submission_id,
                action="DRAFT_CREATED",
                actor=validated_by,
                occurred_at=datetime.now(UTC).isoformat(),
                details=f"return_type={return_type.value} period={return_period}",
            )
        )
        return record

    # ── Public: breach→draft path ──────────────────────────────────────────────

    def create_breach_draft(self, breach_event: BreachEvent) -> SubmissionRecord:
        """Create a DRAFT breach report from a safeguarding.breach.detected event.

        D-recon spec §4 → K-gabriel: breach event triggers a DRAFT submission.
        HITL sign-off is required before the draft reaches GabrielSubmissionPort.

        I-27: This method PROPOSES only — no autonomous FCA submission.
        """
        return self.get_or_create(
            return_type=GabrielReturnType.BREACH_REPORT,
            return_period=breach_event.recon_date,
            validated_by=breach_event.requires_approval_from,
            source_recon_id=breach_event.recon_id,
        )

    # ── Public: pre-submission validation ────────────────────────────────────

    def validate_for_submission(self, record: SubmissionRecord) -> list[str]:
        """Run pre-submission validation; return list of errors (empty = valid).

        Blocks submission if status is SUBMITTED or ACCEPTED (duplicate guard).
        """
        errors: list[str] = []
        if record.status in (GabrielReturnStatus.SUBMITTED, GabrielReturnStatus.ACCEPTED):
            errors.append(
                f"Submission {record.submission_id} already in terminal state {record.status}"
            )
        if not record.return_period:
            errors.append("return_period is required")
        if not record.fca_item_code:
            errors.append("fca_item_code is required")
        return errors
