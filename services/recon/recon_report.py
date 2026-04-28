"""
services/recon/recon_report.py
Daily reconciliation report generator (IL-SAF-01).

Generates structured JSON report from ReconResult for FCA CASS 7 compliance.

I-01: All monetary values are Decimal, serialized as strings.
I-24: Reports are immutable once generated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json

from services.recon.recon_models import ReconResult, ReconStatus


@dataclass(frozen=True)
class ReconReport:
    """Immutable daily reconciliation report (I-24)."""

    report_id: str
    recon_id: str
    recon_date: str
    status: str
    client_funds_total: str  # Decimal as string (I-01, I-05)
    safeguarding_total: str
    difference: str
    discrepancy_count: int
    large_values_flagged: int
    excluded_jurisdictions: tuple[str, ...]
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    report_format: str = "JSON"


class ReconReportGenerator:
    """Generates daily reconciliation reports from ReconResult."""

    def __init__(self) -> None:
        self._reports: list[ReconReport] = []

    def generate(self, result: ReconResult) -> ReconReport:
        """Generate a structured report from a reconciliation result."""
        report = ReconReport(
            report_id=f"rpt-{result.recon_id}",
            recon_id=result.recon_id,
            recon_date=result.recon_date,
            status=result.status.value,
            client_funds_total=str(result.client_funds_total),
            safeguarding_total=str(result.safeguarding_total),
            difference=str(result.difference),
            discrepancy_count=len(result.discrepancies),
            large_values_flagged=result.large_values_flagged,
            excluded_jurisdictions=result.excluded_jurisdictions,
        )
        self._reports.append(report)
        return report

    def to_json(self, report: ReconReport) -> str:
        """Serialize report to JSON string."""
        data = {
            "report_id": report.report_id,
            "recon_id": report.recon_id,
            "recon_date": report.recon_date,
            "status": report.status,
            "client_funds_total": report.client_funds_total,
            "safeguarding_total": report.safeguarding_total,
            "difference": report.difference,
            "discrepancy_count": report.discrepancy_count,
            "large_values_flagged": report.large_values_flagged,
            "excluded_jurisdictions": list(report.excluded_jurisdictions),
            "generated_at": report.generated_at,
            "report_format": report.report_format,
            "fca_compliance": {
                "regulation": "FCA CASS 7",
                "requirement": "Daily safeguarding reconciliation",
                "balanced": report.status == ReconStatus.BALANCED.value,
            },
        }
        return json.dumps(data, indent=2)

    @property
    def reports(self) -> list[ReconReport]:
        return list(self._reports)
