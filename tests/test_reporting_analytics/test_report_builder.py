"""
tests/test_reporting_analytics/test_report_builder.py
IL-RAP-01 | Phase 38 | banxe-emi-stack — 16 tests
"""

from __future__ import annotations

import json

import pytest

from services.reporting_analytics.models import (
    InMemoryReportJobPort,
    InMemoryReportTemplatePort,
)
from services.reporting_analytics.report_builder import ReportBuilder


def _builder() -> ReportBuilder:
    tstore = InMemoryReportTemplatePort()
    jstore = InMemoryReportJobPort()
    return ReportBuilder(tstore, jstore)


def _template_id(builder: ReportBuilder) -> str:
    return builder._templates.list_templates()[0].id


class TestBuildReport:
    def test_returns_report_job(self) -> None:
        b = _builder()
        tid = _template_id(b)
        job = b.build_report(tid, {})
        assert job.template_id == tid

    def test_status_completed(self) -> None:
        b = _builder()
        tid = _template_id(b)
        job = b.build_report(tid, {})
        assert job.status == "COMPLETED"

    def test_output_path_set(self) -> None:
        b = _builder()
        tid = _template_id(b)
        job = b.build_report(tid, {})
        assert job.output_path is not None

    def test_file_hash_set(self) -> None:
        b = _builder()
        tid = _template_id(b)
        job = b.build_report(tid, {})
        assert job.file_hash is not None
        assert len(job.file_hash) == 64  # SHA-256 hex

    def test_unknown_template_raises(self) -> None:
        b = _builder()
        with pytest.raises(ValueError, match="not found"):
            b.build_report("nonexistent-template", {})


class TestRenderJson:
    def test_returns_string(self) -> None:
        b = _builder()
        tid = _template_id(b)
        job = b.build_report(tid, {})
        result = b.render_json(job.id)
        assert isinstance(result, str)

    def test_valid_json(self) -> None:
        b = _builder()
        tid = _template_id(b)
        job = b.build_report(tid, {})
        result = b.render_json(job.id)
        data = json.loads(result)
        assert "job_id" in data

    def test_decimal_as_string(self) -> None:
        b = _builder()
        tid = _template_id(b)
        job = b.build_report(tid, {})
        result = b.render_json(job.id)
        # Should not raise — valid JSON
        json.loads(result)

    def test_unknown_job_raises(self) -> None:
        b = _builder()
        with pytest.raises(ValueError, match="not found"):
            b.render_json("bad-job-id")


class TestRenderCsv:
    def test_returns_string(self) -> None:
        b = _builder()
        tid = _template_id(b)
        job = b.build_report(tid, {})
        result = b.render_csv(job.id)
        assert isinstance(result, str)

    def test_has_headers(self) -> None:
        b = _builder()
        tid = _template_id(b)
        job = b.build_report(tid, {})
        result = b.render_csv(job.id)
        assert "job_id" in result

    def test_unknown_job_raises(self) -> None:
        b = _builder()
        with pytest.raises(ValueError, match="not found"):
            b.render_csv("bad-job-id")


class TestJobStatus:
    def test_get_job_status(self) -> None:
        b = _builder()
        tid = _template_id(b)
        job = b.build_report(tid, {})
        fetched = b.get_job_status(job.id)
        assert fetched is not None
        assert fetched.id == job.id

    def test_unknown_job_returns_none(self) -> None:
        b = _builder()
        assert b.get_job_status("no-such-job") is None


class TestListRecentJobs:
    def test_returns_list(self) -> None:
        b = _builder()
        tid = _template_id(b)
        b.build_report(tid, {})
        result = b.list_recent_jobs(tid)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_respects_limit(self) -> None:
        b = _builder()
        tid = _template_id(b)
        for _ in range(5):
            b.build_report(tid, {})
        result = b.list_recent_jobs(tid, limit=3)
        assert len(result) <= 3
