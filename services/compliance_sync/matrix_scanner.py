"""
services/compliance_sync/matrix_scanner.py
Compliance Matrix Auto-Sync scanner (IL-CMS-01).
Scans S16/FA-01..07 and other blocks for artifact presence.
I-24: ScanLog is append-only.
"""

from __future__ import annotations

from pathlib import Path

from services.compliance_sync.matrix_models import (
    ArtifactStatus,
    ComplianceMatrixReport,
    MatrixEntry,
)

# Base path injected for testability
_DEFAULT_BASE = Path(__file__).resolve().parent.parent.parent


class ArtifactCheckPort:
    """Protocol for checking artifact existence (Protocol DI)."""

    def exists(self, path: str) -> bool:
        return Path(_DEFAULT_BASE / path).exists()


class InMemoryArtifactCheckPort:
    """In-memory stub for testing."""

    def __init__(self, present: set[str] | None = None) -> None:
        self._present: set[str] = present or set()

    def exists(self, path: str) -> bool:
        return path in self._present


# ── Compliance Matrix definitions ─────────────────────────────────────────────
_MATRIX_DEFINITIONS: list[dict] = [
    # S16 / FA block
    {
        "block": "S16/FA",
        "item_id": "FA-01",
        "description": "Blnk/Reconciliation Engine",
        "expected_artifact": "services/recon/reconciliation_engine_v2.py",
    },
    {
        "block": "S16/FA",
        "item_id": "FA-02",
        "description": "bankstatementparser / CAMT.053 parser",
        "expected_artifact": "services/recon/camt053_parser.py",
    },
    {
        "block": "S16/FA",
        "item_id": "FA-03",
        "description": "dbt FIN060 models",
        "expected_artifact": "dbt/models/fin060/fin060_monthly.sql",
    },
    {
        "block": "S16/FA",
        "item_id": "FA-04",
        "description": "pgAudit configuration",
        "expected_artifact": "services/audit/pgaudit_config.py",
    },
    {
        "block": "S16/FA",
        "item_id": "FA-05",
        "description": "WeasyPrint / FIN060 PDF generation",
        "expected_artifact": "services/reporting/fin060_generator_v2.py",
    },
    {
        "block": "S16/FA",
        "item_id": "FA-06",
        "description": "Frankfurter self-hosted FX rates",
        "expected_artifact": "services/fx_rates/frankfurter_client.py",
    },
    {
        "block": "S16/FA",
        "item_id": "FA-07",
        "description": "adorsys PSD2 gateway",
        "expected_artifact": "services/psd2_gateway/adorsys_client.py",
    },
    # S3 block
    {
        "block": "S3",
        "item_id": "S3-12",
        "description": "Midaz MCP Server Integration",
        "expected_artifact": "services/midaz_mcp/midaz_client.py",
    },
    {
        "block": "S3",
        "item_id": "S3-13",
        "description": "Fraud Transaction Tracer",
        "expected_artifact": "services/fraud_tracer/tracer_engine.py",
    },
    # Observability
    {
        "block": "S38",
        "item_id": "OBS-01",
        "description": "Observability Health Aggregator",
        "expected_artifact": "services/observability/health_aggregator.py",
    },
    {
        "block": "S38",
        "item_id": "OBS-02",
        "description": "Compliance Monitor",
        "expected_artifact": "services/observability/compliance_monitor.py",
    },
]


class MatrixScanner:
    """Scans compliance artifacts against the COMPLIANCE-MATRIX definitions.

    I-24: scan_log is append-only.
    """

    def __init__(self, port: ArtifactCheckPort | None = None) -> None:
        self._port: ArtifactCheckPort = port or ArtifactCheckPort()
        self._scan_log: list[ComplianceMatrixReport] = []  # I-24

    def scan_all(self) -> ComplianceMatrixReport:
        """Scan all defined compliance artifacts and return a report."""
        entries: list[MatrixEntry] = []
        for defn in _MATRIX_DEFINITIONS:
            path = defn["expected_artifact"]
            present = self._port.exists(path)
            status = ArtifactStatus.DONE if present else ArtifactStatus.NOT_STARTED
            entries.append(
                MatrixEntry(
                    block=defn["block"],
                    item_id=defn["item_id"],
                    description=defn["description"],
                    expected_artifact=path,
                    actual_path=path if present else None,
                    status=status,
                )
            )
        report = ComplianceMatrixReport.build(entries)
        self._scan_log.append(report)  # I-24
        return report

    def get_gaps(self) -> list[MatrixEntry]:
        """Return only NOT_STARTED and BLOCKED entries."""
        if not self._scan_log:
            self.scan_all()
        latest = self._scan_log[-1]
        return [
            e
            for e in latest.entries
            if e.status in (ArtifactStatus.NOT_STARTED, ArtifactStatus.BLOCKED)
        ]

    @property
    def scan_log(self) -> list[ComplianceMatrixReport]:
        """I-24: append-only scan log."""
        return list(self._scan_log)
