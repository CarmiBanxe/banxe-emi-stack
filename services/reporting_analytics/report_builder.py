"""
services/reporting_analytics/report_builder.py
IL-RAP-01 | Phase 38 | banxe-emi-stack

Report Builder — builds reports from templates, renders JSON/CSV.
I-01: Decimal serialisation as string.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import io
import json
import uuid

from services.reporting_analytics.models import (
    InMemoryReportJobPort,
    InMemoryReportTemplatePort,
    ReportJob,
    ReportJobPort,
    ReportTemplatePort,
)


class _DecimalEncoder(json.JSONEncoder):
    def default(self, o: object) -> object:
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)


class ReportBuilder:
    """Builds and renders reports from templates."""

    def __init__(
        self,
        template_store: ReportTemplatePort | None = None,
        job_store: ReportJobPort | None = None,
    ) -> None:
        self._templates: ReportTemplatePort = template_store or InMemoryReportTemplatePort()
        self._jobs: ReportJobPort = job_store or InMemoryReportJobPort()

    def build_report(self, template_id: str, parameters: dict) -> ReportJob:
        """Create a report job for the given template (stub: COMPLETED)."""
        template = self._templates.get_template(template_id)
        if template is None:
            raise ValueError(f"Template {template_id!r} not found")

        now = datetime.now(UTC)
        output_path = f"/reports/{template_id}/{now.strftime('%Y%m%d%H%M%S')}.json"
        file_content = json.dumps({"template_id": template_id, "parameters": parameters})
        file_hash = hashlib.sha256(file_content.encode()).hexdigest()

        job = ReportJob(
            id=str(uuid.uuid4()),
            template_id=template_id,
            status="COMPLETED",
            parameters=parameters,
            output_path=output_path,
            file_hash=file_hash,
            started_at=now,
            completed_at=now,
            error=None,
        )
        self._jobs.save_job(job)
        return job

    def render_json(self, job_id: str) -> str:
        """Render job result as JSON (Decimal serialized as string)."""
        job = self._jobs.get_job(job_id)
        if job is None:
            raise ValueError(f"ReportJob {job_id!r} not found")

        result = {
            "job_id": job.id,
            "template_id": job.template_id,
            "status": job.status,
            "parameters": job.parameters,
            "output_path": job.output_path,
            "file_hash": job.file_hash,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }
        return json.dumps(result, cls=_DecimalEncoder, indent=2)

    def render_csv(self, job_id: str) -> str:
        """Render job result as CSV string with headers."""
        job = self._jobs.get_job(job_id)
        if job is None:
            raise ValueError(f"ReportJob {job_id!r} not found")

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["job_id", "template_id", "status", "completed_at"])
        writer.writerow(
            [
                job.id,
                job.template_id,
                job.status,
                job.completed_at.isoformat() if job.completed_at else "",
            ]
        )
        return output.getvalue()

    def get_job_status(self, job_id: str) -> ReportJob | None:
        """Return job by ID."""
        return self._jobs.get_job(job_id)

    def list_recent_jobs(self, template_id: str, limit: int = 10) -> list[ReportJob]:
        """Return most recent jobs for a template."""
        jobs = self._jobs.list_jobs(template_id)
        return sorted(jobs, key=lambda j: j.started_at, reverse=True)[:limit]
