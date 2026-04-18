"""
services/reporting_analytics/analytics_agent.py
IL-RAP-01 | Phase 38 | banxe-emi-stack

Analytics Agent — orchestrates report building, schedule changes, exports.
I-27: Schedule changes ALWAYS return HITLProposal.
L1: auto-build and auto-export; L4: schedule changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.reporting_analytics.models import ReportFormat


@dataclass
class HITLProposal:
    action: str
    resource_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


class AnalyticsAgent:
    """Facade agent for reporting and analytics operations."""

    def __init__(self) -> None:
        from services.reporting_analytics.export_engine import ExportEngine
        from services.reporting_analytics.models import (
            InMemoryReportJobPort,
            InMemoryReportTemplatePort,
        )
        from services.reporting_analytics.report_builder import ReportBuilder

        shared_job_store = InMemoryReportJobPort()
        shared_template_store = InMemoryReportTemplatePort()
        self._builder = ReportBuilder(shared_template_store, shared_job_store)
        self._exporter = ExportEngine(shared_job_store, self._builder)

    def process_report_request(self, template_id: str, parameters: dict) -> dict:
        """Auto-build report (L1), return job summary."""
        job = self._builder.build_report(template_id, parameters)
        return {
            "job_id": job.id,
            "template_id": job.template_id,
            "status": job.status,
            "output_path": job.output_path,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }

    def process_schedule_change(self, schedule_id: str, changes: dict) -> HITLProposal:
        """Schedule changes always require human approval (I-27)."""
        return HITLProposal(
            action="update_schedule",
            resource_id=schedule_id,
            requires_approval_from="Analytics Manager",
            reason=f"Schedule change for {schedule_id}: {list(changes.keys())}",
            autonomy_level="L4",
        )

    def process_export_request(
        self,
        job_id: str,
        format: ReportFormat,
        redact_pii: bool,
    ) -> dict:
        """Auto-export report (L1), return export record summary."""
        if format == ReportFormat.CSV:
            record = self._exporter.export_csv(job_id, redact_pii)
        else:
            record = self._exporter.export_json(job_id, redact_pii)

        return {
            "record_id": record.id,
            "job_id": record.job_id,
            "format": record.format.value,
            "file_hash": record.file_hash,
            "pii_redacted": record.pii_redacted,
            "size_bytes": record.size_bytes,
        }

    def get_agent_status(self) -> dict:
        """Return agent operational status."""
        return {
            "agent": "AnalyticsAgent",
            "status": "operational",
            "autonomy_level": "L1/L4",
            "hitl_gates": ["update_schedule"],
            "il": "IL-RAP-01",
        }
