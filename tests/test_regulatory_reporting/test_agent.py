"""
tests/test_regulatory_reporting/test_agent.py
IL-RRA-01 | Phase 14

Tests for RegulatoryReportingAgent orchestration:
  - generate_report (L2: auto generate + validate)
  - submit_report (L4: requires human approval)
  - schedule_report
  - get_audit_log
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from services.regulatory_reporting.models import (
    InMemoryAuditTrail,
    InMemoryRegulatorGateway,
    InMemoryScheduler,
    InMemoryValidator,
    RegulatorTarget,
    ReportPeriod,
    ReportRequest,
    ReportResult,
    ReportStatus,
    ReportType,
    ScheduledReport,
    ScheduleFrequency,
)
from services.regulatory_reporting.regulatory_reporting_agent import RegulatoryReportingAgent
from services.regulatory_reporting.xml_generator import FCARegDataXMLGenerator

# ── Fixtures ──────────────────────────────────────────────────────────────────


def make_agent(
    *,
    force_validation_errors: list[str] | None = None,
    gateway_accept: bool = True,
    scheduler_succeed: bool = True,
) -> tuple[RegulatoryReportingAgent, InMemoryAuditTrail]:
    audit = InMemoryAuditTrail()
    agent = RegulatoryReportingAgent(
        xml_generator=FCARegDataXMLGenerator(),
        validator=InMemoryValidator(force_errors=force_validation_errors),
        audit_trail=audit,
        scheduler=InMemoryScheduler(should_succeed=scheduler_succeed),
        regulator_gateway=InMemoryRegulatorGateway(should_accept=gateway_accept),
    )
    return agent, audit


def make_request(report_type: ReportType = ReportType.FIN060) -> ReportRequest:
    return ReportRequest(
        report_type=report_type,
        period=ReportPeriod(
            start=datetime(2025, 1, 1, tzinfo=UTC),
            end=datetime(2025, 1, 31, tzinfo=UTC),
        ),
        entity_id="FRN123456",
        entity_name="Banxe EMI Ltd",
        submitter_id="test-actor",
    )


# ── generate_report ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_report_validated_status() -> None:
    agent, audit = make_agent()
    result = await agent.generate_report(make_request(), {}, actor="compliance@banxe.com")
    assert result.status == ReportStatus.VALIDATED
    assert result.xml_content is not None
    assert result.validation_errors == []


@pytest.mark.asyncio
async def test_generate_report_creates_two_audit_entries() -> None:
    """Generated + validated audit entries must be written."""
    agent, audit = make_agent()
    await agent.generate_report(make_request(), {}, actor="compliance@banxe.com")
    event_types = [e.event_type for e in audit.entries]
    assert "report.generated" in event_types
    assert "report.validated" in event_types


@pytest.mark.asyncio
async def test_generate_report_failed_validation() -> None:
    agent, audit = make_agent(force_validation_errors=["Missing <FirmRef>"])
    result = await agent.generate_report(make_request(), {}, actor="actor1")
    assert result.status == ReportStatus.FAILED
    assert "Missing <FirmRef>" in result.validation_errors


@pytest.mark.asyncio
async def test_generate_report_failed_validation_audit_entry() -> None:
    agent, audit = make_agent(force_validation_errors=["Bad XML"])
    await agent.generate_report(make_request(), {}, actor="actor1")
    failed = [e for e in audit.entries if e.status == ReportStatus.FAILED]
    assert len(failed) == 1


@pytest.mark.asyncio
async def test_generate_report_all_six_types() -> None:
    agent, _ = make_agent()
    for rtype in ReportType:
        result = await agent.generate_report(make_request(rtype), {}, actor="actor1")
        assert result.report_type == rtype


@pytest.mark.asyncio
async def test_generate_report_entity_id_in_audit() -> None:
    agent, audit = make_agent()
    await agent.generate_report(make_request(), {}, actor="compliance@banxe.com")
    assert all(e.entity_id == "FRN123456" for e in audit.entries)


# ── submit_report ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_report_success() -> None:
    agent, audit = make_agent()
    result = await agent.generate_report(make_request(), {}, actor="actor1")
    submitted = await agent.submit_report(
        make_request(), result, RegulatorTarget.FCA_REGDATA, "compliance@banxe.com"
    )
    assert submitted.status == ReportStatus.SUBMITTED
    assert submitted.submission_ref is not None
    assert submitted.submitted_at is not None


@pytest.mark.asyncio
async def test_submit_report_creates_sysc9_audit_entry() -> None:
    agent, audit = make_agent()
    result = await agent.generate_report(make_request(), {}, actor="actor1")
    await agent.submit_report(make_request(), result, RegulatorTarget.FCA_REGDATA, "actor1")
    submitted_entries = [e for e in audit.entries if e.event_type == "report.submitted"]
    assert len(submitted_entries) == 1
    assert submitted_entries[0].details["submission_ref"] is not None


@pytest.mark.asyncio
async def test_submit_report_requires_validated_status() -> None:
    """L4 gate: must not submit a FAILED report."""
    agent, _ = make_agent()
    failed_result = ReportResult(
        request_id="rep-001",
        report_type=ReportType.FIN060,
        status=ReportStatus.FAILED,
        xml_content="<bad/>",
        pdf_content=None,
        validation_errors=["error"],
        submission_ref=None,
        generated_at=datetime.now(UTC),
    )
    with pytest.raises(ValueError, match="not ready to submit"):
        await agent.submit_report(
            make_request(), failed_result, RegulatorTarget.FCA_REGDATA, "actor1"
        )


@pytest.mark.asyncio
async def test_submit_report_gateway_rejection_raises() -> None:
    agent, audit = make_agent(gateway_accept=False)
    result = await agent.generate_report(make_request(), {}, actor="actor1")
    with pytest.raises(ValueError):
        await agent.submit_report(make_request(), result, RegulatorTarget.FCA_REGDATA, "actor1")
    # Failure audit entry must be written
    failed = [e for e in audit.entries if e.event_type == "report.submission_failed"]
    assert len(failed) == 1


@pytest.mark.asyncio
async def test_submit_report_regulator_target_in_result() -> None:
    agent, _ = make_agent()
    result = await agent.generate_report(make_request(), {}, actor="actor1")
    submitted = await agent.submit_report(
        make_request(), result, RegulatorTarget.NCA_GATEWAY, "actor1"
    )
    assert submitted.regulator_target == RegulatorTarget.NCA_GATEWAY


# ── schedule_report ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_schedule_report_success() -> None:
    agent, _ = make_agent()
    schedule = ScheduledReport(
        id="sched-001",
        report_type=ReportType.FIN060,
        entity_id="FRN123456",
        frequency=ScheduleFrequency.MONTHLY,
        next_run_at=datetime.now(UTC),
        template_version="v3",
    )
    success = await agent.schedule_report(schedule, "admin@banxe.com")
    assert success is True


@pytest.mark.asyncio
async def test_schedule_report_failure() -> None:
    agent, _ = make_agent(scheduler_succeed=False)
    schedule = ScheduledReport(
        id="sched-002",
        report_type=ReportType.FIN060,
        entity_id="FRN123456",
        frequency=ScheduleFrequency.MONTHLY,
        next_run_at=datetime.now(UTC),
        template_version="v3",
    )
    success = await agent.schedule_report(schedule, "admin@banxe.com")
    assert success is False


@pytest.mark.asyncio
async def test_cancel_schedule() -> None:
    agent, _ = make_agent()
    success = await agent.cancel_schedule("sched-001", "admin@banxe.com")
    assert success is True


# ── get_audit_log ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_audit_log_returns_dicts() -> None:
    agent, _ = make_agent()
    await agent.generate_report(make_request(), {}, actor="actor1")
    log = await agent.get_audit_log()
    assert isinstance(log, list)
    assert len(log) >= 1
    assert "event_type" in log[0]
    assert "created_at" in log[0]


@pytest.mark.asyncio
async def test_get_audit_log_filter_by_entity() -> None:
    agent, _ = make_agent()
    await agent.generate_report(make_request(), {}, actor="actor1")
    log = await agent.get_audit_log(entity_id="FRN123456")
    assert all(e["entity_id"] == "FRN123456" for e in log)


@pytest.mark.asyncio
async def test_get_audit_log_filter_by_type() -> None:
    agent, _ = make_agent()
    await agent.generate_report(make_request(ReportType.FIN060), {}, actor="actor1")
    await agent.generate_report(make_request(ReportType.FIN071), {}, actor="actor1")
    log = await agent.get_audit_log(report_type=ReportType.FIN060)
    assert all(e["report_type"] == "FIN060" for e in log)
