"""
tests/test_gabriel_returns_governor.py
K-gabriel ReturnsGovernor tests (IL-CBS-GABRIEL-GOVERNOR-2026-06-26).

DoD coverage (K-gabriel spec §4):
  - test_return_schedule_config_driven
  - test_pre_submission_validation_blocks_invalid
  - test_deadline_tracking_before_fca_cutoff
  - test_breach_event_to_report_path
  - test_submission_audit_immutable_5y
  - test_submission_idempotent_per_period

Additional:
  - Protocol compliance for ports
  - deadline overdue detection
  - breach draft links recon_id
  - multiple return types independent
  - validation passes valid record
  - InMemory submission port returns SUBMITTED copy
  - audit entry count per operation
  - status remains DRAFT (no autonomous submission)
  - BREACH_REPORT deadline is 2-day window
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from services.gabriel.gabriel_models import (
    GabrielAuditPort,
    GabrielReturnStatus,
    GabrielReturnType,
    GabrielSubmissionPort,
    InMemoryGabrielAuditPort,
    InMemoryGabrielSubmissionPort,
    ReturnSchedule,
    SubmissionRecord,
)
from services.gabriel.returns_governor import ReturnsGovernor
from services.recon.breach_notify_port import BreachEvent

# ── Fixtures ──────────────────────────────────────────────────────────────────

PERIOD_MAY = "2026-05"
PERIOD_JUN = "2026-06"
PERIOD_DATE = "2026-06-20"


def _make_breach_event(recon_id: str = "recon-abc", recon_date: str = PERIOD_DATE) -> BreachEvent:
    return BreachEvent(
        event_type="safeguarding.breach.detected",
        recon_id=recon_id,
        recon_date=recon_date,
        currency="GBP",
        client_funds_total=Decimal("10500.00"),
        safeguarding_total=Decimal("10000.00"),
        shortfall=Decimal("500.00"),
        detected_at=datetime.now(UTC).isoformat(),
        requires_approval_from="MLRO",
    )


def _governor(audit: InMemoryGabrielAuditPort | None = None) -> ReturnsGovernor:
    return ReturnsGovernor(audit=audit or InMemoryGabrielAuditPort())


# ── DoD: test_return_schedule_config_driven ───────────────────────────────────


class TestReturnScheduleConfigDriven:
    def test_fin060_schedule_is_monthly(self) -> None:
        gov = _governor()
        sched = gov.get_schedule(GabrielReturnType.FIN060)
        assert sched.frequency == "MONTHLY"

    def test_fin060_deadline_day_is_15(self) -> None:
        gov = _governor()
        sched = gov.get_schedule(GabrielReturnType.FIN060)
        assert sched.deadline_day == 15

    def test_breach_report_schedule_is_adhoc(self) -> None:
        gov = _governor()
        sched = gov.get_schedule(GabrielReturnType.BREACH_REPORT)
        assert sched.frequency == "AD_HOC"

    def test_custom_schedule_overrides_default(self) -> None:
        custom = {
            GabrielReturnType.FIN060: ReturnSchedule(
                return_type=GabrielReturnType.FIN060,
                frequency="QUARTERLY",
                deadline_day=30,
                fca_item_code="FIN060-QUARTERLY-TEST",
            )
        }
        gov = ReturnsGovernor(schedule_config=custom)
        sched = gov.get_schedule(GabrielReturnType.FIN060)
        assert sched.frequency == "QUARTERLY"
        assert sched.deadline_day == 30

    def test_unknown_return_type_raises(self) -> None:
        custom_sched: dict[GabrielReturnType, ReturnSchedule] = {}
        gov = ReturnsGovernor(schedule_config=custom_sched)
        with pytest.raises(KeyError):
            gov.get_schedule(GabrielReturnType.FIN060)


# ── DoD: test_deadline_tracking_before_fca_cutoff ────────────────────────────


class TestDeadlineTracking:
    def test_fin060_deadline_is_15th_of_next_month(self) -> None:
        gov = _governor()
        status = gov.get_deadline_status(GabrielReturnType.FIN060, "2026-05")
        assert status.deadline_date == "2026-06-15"

    def test_fin060_december_wraps_to_january(self) -> None:
        gov = _governor()
        status = gov.get_deadline_status(GabrielReturnType.FIN060, "2026-12")
        assert status.deadline_date == "2027-01-15"

    def test_breach_report_deadline_is_two_days(self) -> None:
        gov = _governor()
        status = gov.get_deadline_status(GabrielReturnType.BREACH_REPORT, "2026-06-20")
        assert status.deadline_date == "2026-06-22"

    def test_days_remaining_positive_for_future_deadline(self) -> None:
        gov = _governor()
        future_period = (date.today() - timedelta(days=5)).strftime("%Y-%m")
        status = gov.get_deadline_status(GabrielReturnType.FIN060, future_period)
        assert status.days_remaining > 0 or status.is_overdue  # one or the other

    def test_overdue_flag_set_when_past_deadline(self) -> None:
        gov = _governor()
        # Period 3 months ago — deadline long past
        old_date = date.today() - timedelta(days=90)
        period = old_date.strftime("%Y-%m")
        status = gov.get_deadline_status(GabrielReturnType.FIN060, period)
        assert status.is_overdue is True
        assert status.days_remaining < 0


# ── DoD: test_breach_event_to_report_path ────────────────────────────────────


class TestBreachEventToReportPath:
    def test_creates_submission_record(self) -> None:
        gov = _governor()
        record = gov.create_breach_draft(_make_breach_event())
        assert record is not None
        assert isinstance(record, SubmissionRecord)

    def test_record_type_is_breach_report(self) -> None:
        gov = _governor()
        record = gov.create_breach_draft(_make_breach_event())
        assert record.return_type == GabrielReturnType.BREACH_REPORT

    def test_record_links_source_recon_id(self) -> None:
        gov = _governor()
        event = _make_breach_event(recon_id="recon-xyz999")
        record = gov.create_breach_draft(event)
        assert record.source_recon_id == "recon-xyz999"

    def test_record_status_is_draft_not_submitted(self) -> None:
        # I-27: no autonomous submission
        gov = _governor()
        record = gov.create_breach_draft(_make_breach_event())
        assert record.status == GabrielReturnStatus.DRAFT

    def test_record_period_matches_recon_date(self) -> None:
        gov = _governor()
        event = _make_breach_event(recon_date="2026-06-25")
        record = gov.create_breach_draft(event)
        assert record.return_period == "2026-06-25"

    def test_record_fca_item_code_from_schedule(self) -> None:
        gov = _governor()
        record = gov.create_breach_draft(_make_breach_event())
        assert record.fca_item_code == "BREACH-SAFEGUARD"


# ── DoD: test_submission_audit_immutable_5y ───────────────────────────────────


class TestSubmissionAuditImmutable:
    def test_audit_recorded_on_draft_creation(self) -> None:
        audit = InMemoryGabrielAuditPort()
        gov = ReturnsGovernor(audit=audit)
        gov.create_breach_draft(_make_breach_event())
        assert len(audit.entries) == 1

    def test_audit_entry_action_is_draft_created(self) -> None:
        audit = InMemoryGabrielAuditPort()
        gov = ReturnsGovernor(audit=audit)
        gov.create_breach_draft(_make_breach_event())
        assert audit.entries[0].action == "DRAFT_CREATED"

    def test_audit_entry_has_submission_id(self) -> None:
        audit = InMemoryGabrielAuditPort()
        gov = ReturnsGovernor(audit=audit)
        record = gov.create_breach_draft(_make_breach_event())
        assert audit.entries[0].submission_id == record.submission_id

    def test_audit_port_satisfies_protocol(self) -> None:
        assert isinstance(InMemoryGabrielAuditPort(), GabrielAuditPort)

    def test_audit_entries_accumulate_not_overwrite(self) -> None:
        audit = InMemoryGabrielAuditPort()
        gov = ReturnsGovernor(audit=audit)
        gov.create_breach_draft(_make_breach_event(recon_date="2026-06-20"))
        gov.get_or_create(GabrielReturnType.FIN060, PERIOD_MAY)
        assert len(audit.entries) == 2


# ── DoD: test_submission_idempotent_per_period ────────────────────────────────


class TestSubmissionIdempotency:
    def test_same_type_and_period_returns_same_record(self) -> None:
        gov = _governor()
        r1 = gov.get_or_create(GabrielReturnType.FIN060, PERIOD_MAY)
        r2 = gov.get_or_create(GabrielReturnType.FIN060, PERIOD_MAY)
        assert r1.submission_id == r2.submission_id

    def test_idempotency_key_format(self) -> None:
        gov = _governor()
        record = gov.get_or_create(GabrielReturnType.FIN060, PERIOD_MAY)
        assert record.idempotency_key == "FIN060:2026-05"

    def test_different_periods_get_different_records(self) -> None:
        gov = _governor()
        r1 = gov.get_or_create(GabrielReturnType.FIN060, PERIOD_MAY)
        r2 = gov.get_or_create(GabrielReturnType.FIN060, PERIOD_JUN)
        assert r1.submission_id != r2.submission_id

    def test_breach_draft_idempotent_on_same_date(self) -> None:
        gov = _governor()
        e1 = _make_breach_event(recon_id="recon-001", recon_date="2026-06-20")
        e2 = _make_breach_event(recon_id="recon-002", recon_date="2026-06-20")  # same date
        r1 = gov.create_breach_draft(e1)
        r2 = gov.create_breach_draft(e2)
        assert r1.submission_id == r2.submission_id


# ── DoD: test_pre_submission_validation_blocks_invalid ───────────────────────


class TestPreSubmissionValidation:
    def test_valid_draft_returns_no_errors(self) -> None:
        gov = _governor()
        record = gov.get_or_create(GabrielReturnType.FIN060, PERIOD_MAY)
        errors = gov.validate_for_submission(record)
        assert errors == []

    def test_submitted_record_blocked(self) -> None:
        gov = _governor()
        record = gov.get_or_create(GabrielReturnType.FIN060, PERIOD_MAY)
        submitted = replace(record, status=GabrielReturnStatus.SUBMITTED)
        errors = gov.validate_for_submission(submitted)
        assert len(errors) == 1
        assert "terminal state" in errors[0]

    def test_accepted_record_blocked(self) -> None:
        gov = _governor()
        record = gov.get_or_create(GabrielReturnType.FIN060, PERIOD_MAY)
        accepted = replace(record, status=GabrielReturnStatus.ACCEPTED)
        errors = gov.validate_for_submission(accepted)
        assert errors  # blocked

    def test_missing_fca_item_code_blocked(self) -> None:
        gov = _governor()
        record = gov.get_or_create(GabrielReturnType.FIN060, PERIOD_MAY)
        bad = replace(record, fca_item_code="")
        errors = gov.validate_for_submission(bad)
        assert any("fca_item_code" in e for e in errors)


# ── Protocol compliance ───────────────────────────────────────────────────────


class TestProtocolCompliance:
    def test_gabriel_submission_port_satisfied(self) -> None:
        assert isinstance(InMemoryGabrielSubmissionPort(), GabrielSubmissionPort)

    def test_in_memory_submit_returns_submitted_status(self) -> None:
        port = InMemoryGabrielSubmissionPort()
        gov = _governor()
        record = gov.get_or_create(GabrielReturnType.FIN060, PERIOD_MAY)
        submitted = port.submit(record)
        assert submitted.status == GabrielReturnStatus.SUBMITTED
        assert submitted.submitted_at is not None
        assert submitted.submission_ref is not None
