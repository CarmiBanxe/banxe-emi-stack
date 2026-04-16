"""
tests/test_regulatory_reporting/test_audit_trail.py
IL-RRA-01 | Phase 14

Tests for audit trail factory functions and InMemoryAuditTrail.
I-24: append-only — every audit test must verify no mutation of existing entries.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from services.regulatory_reporting.audit_trail import (
    make_failed_entry,
    make_generated_entry,
    make_submitted_entry,
    make_validated_entry,
)
from services.regulatory_reporting.models import (
    InMemoryAuditTrail,
    RegulatorTarget,
    ReportPeriod,
    ReportRequest,
    ReportResult,
    ReportStatus,
    ReportType,
    ValidationResult,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


def make_request() -> ReportRequest:
    return ReportRequest(
        report_type=ReportType.FIN060,
        period=ReportPeriod(
            start=datetime(2025, 1, 1, tzinfo=UTC),
            end=datetime(2025, 1, 31, tzinfo=UTC),
        ),
        entity_id="FRN123456",
        entity_name="Banxe EMI Ltd",
        submitter_id="tester",
    )


def make_result(status: ReportStatus = ReportStatus.VALIDATED) -> ReportResult:
    return ReportResult(
        request_id="rep-001",
        report_type=ReportType.FIN060,
        status=status,
        xml_content="<xml/>",
        pdf_content=None,
        validation_errors=[],
        submission_ref=None,
        generated_at=datetime.now(UTC),
        regulator_target=RegulatorTarget.FCA_REGDATA,
    )


# ── Factory functions ─────────────────────────────────────────────────────────


def test_make_generated_entry_event_type() -> None:
    entry = make_generated_entry(make_request(), make_result(), "actor1")
    assert entry.event_type == "report.generated"


def test_make_generated_entry_status_matches_result() -> None:
    entry = make_generated_entry(make_request(), make_result(ReportStatus.DRAFT), "actor1")
    assert entry.status == ReportStatus.DRAFT


def test_make_generated_entry_details_has_xml_length() -> None:
    entry = make_generated_entry(make_request(), make_result(), "actor1")
    assert "xml_length" in entry.details


def test_make_generated_entry_unique_ids() -> None:
    e1 = make_generated_entry(make_request(), make_result(), "actor1")
    e2 = make_generated_entry(make_request(), make_result(), "actor1")
    assert e1.id != e2.id


def test_make_validated_entry_valid_status() -> None:
    validation = ValidationResult(
        is_valid=True,
        errors=[],
        warnings=[],
        schema_version="xsd-1.0",
        validated_at=datetime.now(UTC),
    )
    entry = make_validated_entry(make_request(), make_result(), validation, "actor1")
    assert entry.status == ReportStatus.VALIDATED
    assert entry.event_type == "report.validated"


def test_make_validated_entry_invalid_status() -> None:
    validation = ValidationResult(
        is_valid=False,
        errors=["Missing <FirmRef>"],
        warnings=[],
        schema_version="xsd-1.0",
        validated_at=datetime.now(UTC),
    )
    entry = make_validated_entry(make_request(), make_result(), validation, "actor1")
    assert entry.status == ReportStatus.FAILED
    assert entry.details["error_count"] == 1


def test_make_submitted_entry_sysc9() -> None:
    entry = make_submitted_entry(
        make_request(),
        make_result(),
        submission_ref="REF-ABCDEF01",
        actor="compliance@banxe.com",
        target=RegulatorTarget.FCA_REGDATA,
    )
    assert entry.event_type == "report.submitted"
    assert entry.status == ReportStatus.SUBMITTED
    assert entry.details["submission_ref"] == "REF-ABCDEF01"
    assert entry.regulator_target == RegulatorTarget.FCA_REGDATA


def test_make_failed_entry_default_event_type() -> None:
    entry = make_failed_entry(make_request(), "rep-001", "Connection error", "actor1")
    assert entry.event_type == "report.failed"
    assert entry.status == ReportStatus.FAILED
    assert "Connection error" in entry.details["error"]


def test_make_failed_entry_custom_event_type() -> None:
    entry = make_failed_entry(
        make_request(),
        "rep-001",
        "Gateway timeout",
        "actor1",
        event_type="report.submission_failed",
    )
    assert entry.event_type == "report.submission_failed"


# ── InMemoryAuditTrail ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_inmemory_append_and_query_all() -> None:
    trail = InMemoryAuditTrail()
    entry = make_generated_entry(make_request(), make_result(), "actor1")
    await trail.append(entry)
    results = await trail.query()
    assert len(results) == 1
    assert results[0].id == entry.id


@pytest.mark.asyncio
async def test_inmemory_append_is_append_only() -> None:
    """Entries are never removed or replaced — I-24."""
    trail = InMemoryAuditTrail()
    e1 = make_generated_entry(make_request(), make_result(), "actor1")
    e2 = make_validated_entry(
        make_request(),
        make_result(),
        ValidationResult(
            is_valid=True,
            errors=[],
            warnings=[],
            schema_version="v1",
            validated_at=datetime.now(UTC),
        ),
        "actor1",
    )
    await trail.append(e1)
    await trail.append(e2)
    results = await trail.query()
    assert len(results) == 2


@pytest.mark.asyncio
async def test_inmemory_filter_by_report_type() -> None:
    trail = InMemoryAuditTrail()
    req71 = ReportRequest(
        report_type=ReportType.FIN071,
        period=ReportPeriod(
            start=datetime(2025, 1, 1, tzinfo=UTC), end=datetime(2025, 1, 31, tzinfo=UTC)
        ),
        entity_id="FRN000001",
        entity_name="Other Firm",
        submitter_id="x",
    )
    res71 = ReportResult(
        request_id="rep-071",
        report_type=ReportType.FIN071,
        status=ReportStatus.VALIDATED,
        xml_content="<xml/>",
        pdf_content=None,
        validation_errors=[],
        submission_ref=None,
        generated_at=datetime.now(UTC),
    )
    await trail.append(make_generated_entry(make_request(), make_result(), "actor1"))
    await trail.append(make_generated_entry(req71, res71, "actor1"))
    results = await trail.query(report_type=ReportType.FIN060)
    assert all(e.report_type == ReportType.FIN060 for e in results)


@pytest.mark.asyncio
async def test_inmemory_filter_by_entity_id() -> None:
    trail = InMemoryAuditTrail()
    await trail.append(make_generated_entry(make_request(), make_result(), "actor1"))
    results_match = await trail.query(entity_id="FRN123456")
    results_no_match = await trail.query(entity_id="FRN999999")
    assert len(results_match) == 1
    assert len(results_no_match) == 0


@pytest.mark.asyncio
async def test_inmemory_query_empty_trail() -> None:
    trail = InMemoryAuditTrail()
    results = await trail.query()
    assert results == []


@pytest.mark.asyncio
async def test_inmemory_entry_is_immutable() -> None:
    """AuditEntry is frozen dataclass — immutability enforced."""
    entry = make_generated_entry(make_request(), make_result(), "actor1")
    with pytest.raises((AttributeError, TypeError)):
        entry.actor = "tampered"  # type: ignore[misc]
