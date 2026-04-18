"""
services/reporting_analytics/export_engine.py
IL-RAP-01 | Phase 38 | banxe-emi-stack

Export Engine — exports reports to JSON/CSV, SHA-256 integrity, PII redaction.
I-12: SHA-256 hash for all exports.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import re
import uuid

from services.reporting_analytics.models import (
    ExportRecord,
    InMemoryReportJobPort,
    ReportFormat,
    ReportJobPort,
)
from services.reporting_analytics.report_builder import ReportBuilder

_IBAN_RE = re.compile(r"[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}[A-Z0-9]*")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


class ExportEngine:
    """Handles report exports with PII redaction and integrity hashing."""

    def __init__(
        self,
        job_store: ReportJobPort | None = None,
        builder: ReportBuilder | None = None,
    ) -> None:
        self._jobs: ReportJobPort = job_store or InMemoryReportJobPort()
        self._builder = builder or ReportBuilder(job_store=self._jobs)
        self._records: dict[str, ExportRecord] = {}

    def export_json(self, job_id: str, redact_pii: bool = True) -> ExportRecord:
        """Render JSON, compute SHA-256 hash (I-12), create ExportRecord."""
        content = self._builder.render_json(job_id)
        if redact_pii:
            content = self.redact_pii(content)
        file_hash = _sha256(content)
        record = ExportRecord(
            id=str(uuid.uuid4()),
            job_id=job_id,
            format=ReportFormat.JSON,
            file_hash=file_hash,
            size_bytes=len(content.encode()),
            pii_redacted=redact_pii,
            created_at=datetime.now(UTC),
            created_by="system",
        )
        self._records[record.id] = record
        return record

    def export_csv(self, job_id: str, redact_pii: bool = True) -> ExportRecord:
        """Render CSV, compute SHA-256 hash (I-12), create ExportRecord."""
        content = self._builder.render_csv(job_id)
        if redact_pii:
            content = self.redact_pii(content)
        file_hash = _sha256(content)
        record = ExportRecord(
            id=str(uuid.uuid4()),
            job_id=job_id,
            format=ReportFormat.CSV,
            file_hash=file_hash,
            size_bytes=len(content.encode()),
            pii_redacted=redact_pii,
            created_at=datetime.now(UTC),
            created_by="system",
        )
        self._records[record.id] = record
        return record

    def redact_pii(self, data: str) -> str:
        """Replace IBAN, email patterns with [REDACTED]."""
        data = _IBAN_RE.sub("[REDACTED]", data)
        data = _EMAIL_RE.sub("[REDACTED]", data)
        return data

    def get_export_record(self, record_id: str) -> ExportRecord | None:
        """Return export record by ID."""
        return self._records.get(record_id)

    def list_exports(self, job_id: str) -> list[ExportRecord]:
        """List all exports for a given job."""
        return [r for r in self._records.values() if r.job_id == job_id]
