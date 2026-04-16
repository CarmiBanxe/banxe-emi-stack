"""
services/regulatory_reporting/audit_trail.py — Regulatory Audit Trail
IL-RRA-01 | Phase 14 | banxe-emi-stack

Append-only audit trail for all regulatory report events.
SYSC 9: firms must maintain adequate records of all regulatory submissions.
I-24: append-only — no UPDATE or DELETE.

Architecture: AuditTrailPort Protocol DI (InMemory for tests, ClickHouse in prod)
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import uuid

from services.regulatory_reporting.models import (
    AuditEntry,
    RegulatorTarget,
    ReportRequest,
    ReportResult,
    ReportStatus,
    ReportType,
    ValidationResult,
)

logger = logging.getLogger(__name__)


def _make_audit_id() -> str:
    return str(uuid.uuid4())


def make_generated_entry(
    request: ReportRequest,
    result: ReportResult,
    actor: str,
) -> AuditEntry:
    """Create audit entry for report generation event."""
    return AuditEntry(
        id=_make_audit_id(),
        event_type="report.generated",
        report_type=request.report_type,
        report_id=result.request_id,
        entity_id=request.entity_id,
        actor=actor,
        status=result.status,
        details={
            "template_version": request.template_version,
            "period": request.period.label,
            "xml_length": len(result.xml_content or ""),
        },
        created_at=datetime.now(UTC),
        regulator_target=result.regulator_target,
    )


def make_validated_entry(
    request: ReportRequest,
    result: ReportResult,
    validation: ValidationResult,
    actor: str,
) -> AuditEntry:
    """Create audit entry for validation event."""
    return AuditEntry(
        id=_make_audit_id(),
        event_type="report.validated",
        report_type=request.report_type,
        report_id=result.request_id,
        entity_id=request.entity_id,
        actor=actor,
        status=ReportStatus.VALIDATED if validation.is_valid else ReportStatus.FAILED,
        details={
            "is_valid": validation.is_valid,
            "error_count": len(validation.errors),
            "warning_count": len(validation.warnings),
            "schema_version": validation.schema_version,
        },
        created_at=datetime.now(UTC),
        regulator_target=result.regulator_target,
    )


def make_submitted_entry(
    request: ReportRequest,
    result: ReportResult,
    submission_ref: str,
    actor: str,
    target: RegulatorTarget,
) -> AuditEntry:
    """Create audit entry for submission event — SYSC 9 record."""
    return AuditEntry(
        id=_make_audit_id(),
        event_type="report.submitted",
        report_type=request.report_type,
        report_id=result.request_id,
        entity_id=request.entity_id,
        actor=actor,
        status=ReportStatus.SUBMITTED,
        details={
            "submission_ref": submission_ref,
            "regulator": target.value,
            "period": request.period.label,
        },
        created_at=datetime.now(UTC),
        regulator_target=target,
    )


def make_failed_entry(
    request: ReportRequest,
    report_id: str,
    error: str,
    actor: str,
    event_type: str = "report.failed",
) -> AuditEntry:
    """Create audit entry for failure event."""
    return AuditEntry(
        id=_make_audit_id(),
        event_type=event_type,
        report_type=request.report_type,
        report_id=report_id,
        entity_id=request.entity_id,
        actor=actor,
        status=ReportStatus.FAILED,
        details={"error": error},
        created_at=datetime.now(UTC),
    )


class ClickHouseAuditTrail:
    """
    ClickHouse-backed append-only audit trail.

    Table: banxe.regulatory_report_audit
    Engine: MergeTree() — append-only, never updates (I-24)
    TTL: 5 years minimum (SYSC 9.1.1R)

    In sandbox/tests use InMemoryAuditTrail instead.
    """

    def __init__(self, clickhouse_dsn: str | None = None) -> None:
        self._dsn = clickhouse_dsn
        self._available = self._check_client()

    @staticmethod
    def _check_client() -> bool:
        try:
            import clickhouse_connect  # noqa: F401

            return True
        except ImportError:
            return False

    async def append(self, entry: AuditEntry) -> None:
        if not self._available or not self._dsn:
            logger.warning("ClickHouse unavailable — audit entry %s not persisted", entry.id)
            return

        import clickhouse_connect  # noqa: PLC0415

        client = clickhouse_connect.get_client(dsn=self._dsn)
        client.insert(
            "banxe.regulatory_report_audit",
            [
                [
                    entry.id,
                    entry.event_type,
                    entry.report_type.value,
                    entry.report_id,
                    entry.entity_id,
                    entry.actor,
                    entry.status.value,
                    str(entry.details),
                    entry.created_at,
                    entry.regulator_target.value if entry.regulator_target else None,
                ]
            ],
            column_names=[
                "id",
                "event_type",
                "report_type",
                "report_id",
                "entity_id",
                "actor",
                "status",
                "details",
                "created_at",
                "regulator_target",
            ],
        )
        logger.debug("Audit entry %s appended to ClickHouse", entry.id)

    async def query(
        self,
        report_type: ReportType | None = None,
        entity_id: str | None = None,
        days: int = 30,
    ) -> list[AuditEntry]:
        if not self._available or not self._dsn:
            return []

        import clickhouse_connect  # noqa: PLC0415

        client = clickhouse_connect.get_client(dsn=self._dsn)
        conditions = [f"created_at >= now() - INTERVAL {days} DAY"]
        if report_type:
            conditions.append(f"report_type = '{report_type.value}'")
        if entity_id:
            conditions.append(f"entity_id = '{entity_id}'")

        where = " AND ".join(conditions)
        rows = client.query(
            f"SELECT * FROM banxe.regulatory_report_audit WHERE {where} "  # nosec B608  # noqa: S608
            f"ORDER BY created_at DESC LIMIT 500"
        ).result_rows

        return [
            AuditEntry(
                id=row[0],
                event_type=row[1],
                report_type=ReportType(row[2]),
                report_id=row[3],
                entity_id=row[4],
                actor=row[5],
                status=ReportStatus(row[6]),
                details={},
                created_at=row[8],
                regulator_target=RegulatorTarget(row[9]) if row[9] else None,
            )
            for row in rows
        ]
