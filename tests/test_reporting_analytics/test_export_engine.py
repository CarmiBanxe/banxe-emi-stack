"""
tests/test_reporting_analytics/test_export_engine.py
IL-RAP-01 | Phase 38 | banxe-emi-stack — 16 tests
"""

from __future__ import annotations

from services.reporting_analytics.export_engine import ExportEngine
from services.reporting_analytics.models import (
    InMemoryReportJobPort,
    InMemoryReportTemplatePort,
    ReportFormat,
)
from services.reporting_analytics.report_builder import ReportBuilder


def _engine() -> tuple[ExportEngine, str]:
    tstore = InMemoryReportTemplatePort()
    jstore = InMemoryReportJobPort()
    builder = ReportBuilder(tstore, jstore)
    tid = tstore.list_templates()[0].id
    job = builder.build_report(tid, {})
    engine = ExportEngine(jstore, builder)
    return engine, job.id


class TestExportJson:
    def test_returns_export_record(self) -> None:
        engine, job_id = _engine()
        record = engine.export_json(job_id)
        assert record.job_id == job_id

    def test_format_is_json(self) -> None:
        engine, job_id = _engine()
        record = engine.export_json(job_id)
        assert record.format == ReportFormat.JSON

    def test_file_hash_is_sha256(self) -> None:
        engine, job_id = _engine()
        record = engine.export_json(job_id)
        assert len(record.file_hash) == 64

    def test_pii_redacted_flag_set(self) -> None:
        engine, job_id = _engine()
        record = engine.export_json(job_id, redact_pii=True)
        assert record.pii_redacted is True

    def test_pii_not_redacted_flag(self) -> None:
        engine, job_id = _engine()
        record = engine.export_json(job_id, redact_pii=False)
        assert record.pii_redacted is False


class TestExportCsv:
    def test_returns_export_record(self) -> None:
        engine, job_id = _engine()
        record = engine.export_csv(job_id)
        assert record.job_id == job_id

    def test_format_is_csv(self) -> None:
        engine, job_id = _engine()
        record = engine.export_csv(job_id)
        assert record.format == ReportFormat.CSV

    def test_size_bytes_positive(self) -> None:
        engine, job_id = _engine()
        record = engine.export_csv(job_id)
        assert record.size_bytes > 0


class TestRedactPii:
    def test_redacts_email(self) -> None:
        engine, _ = _engine()
        data = "Contact: user@example.com for info"
        result = engine.redact_pii(data)
        assert "user@example.com" not in result
        assert "[REDACTED]" in result

    def test_redacts_iban(self) -> None:
        engine, _ = _engine()
        data = "IBAN: GB29NWBK60161331926819 transfer"
        result = engine.redact_pii(data)
        assert "GB29NWBK60161331926819" not in result
        assert "[REDACTED]" in result

    def test_non_pii_not_redacted(self) -> None:
        engine, _ = _engine()
        data = "Normal text without PII"
        result = engine.redact_pii(data)
        assert result == data

    def test_multiple_emails_redacted(self) -> None:
        engine, _ = _engine()
        data = "From: a@b.com To: c@d.com"
        result = engine.redact_pii(data)
        assert "a@b.com" not in result
        assert "c@d.com" not in result


class TestListExports:
    def test_returns_list(self) -> None:
        engine, job_id = _engine()
        engine.export_json(job_id)
        exports = engine.list_exports(job_id)
        assert len(exports) >= 1

    def test_unknown_job_returns_empty(self) -> None:
        engine, _ = _engine()
        exports = engine.list_exports("no-such-job")
        assert exports == []

    def test_get_export_record_by_id(self) -> None:
        engine, job_id = _engine()
        record = engine.export_json(job_id)
        fetched = engine.get_export_record(record.id)
        assert fetched is not None
        assert fetched.id == record.id
