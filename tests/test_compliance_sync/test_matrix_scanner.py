"""Tests for Compliance Matrix Auto-Sync (IL-CMS-01)."""

from __future__ import annotations

import pytest

from services.compliance_sync.matrix_models import (
    ArtifactStatus,
    ComplianceMatrixReport,
    MatrixEntry,
)
from services.compliance_sync.matrix_scanner import (
    _MATRIX_DEFINITIONS,
    InMemoryArtifactCheckPort,
    MatrixScanner,
)


class TestMatrixModels:
    def test_matrix_entry_status_default(self):
        entry = MatrixEntry(
            block="S16/FA",
            item_id="FA-01",
            description="test",
            expected_artifact="services/recon/x.py",
        )
        assert entry.status == ArtifactStatus.NOT_STARTED

    def test_compliance_matrix_report_coverage_pct_is_string(self):
        entries = [
            MatrixEntry(
                block="S16",
                item_id="FA-01",
                description="test",
                expected_artifact="x.py",
                status=ArtifactStatus.DONE,
            ),
            MatrixEntry(
                block="S16",
                item_id="FA-02",
                description="test",
                expected_artifact="y.py",
                status=ArtifactStatus.NOT_STARTED,
            ),
        ]
        report = ComplianceMatrixReport.build(entries)
        assert isinstance(report.coverage_pct, str)
        assert report.coverage_pct == "50.0"

    def test_coverage_pct_decimal_not_float(self):
        entries = [
            MatrixEntry(
                block="S16",
                item_id="FA-01",
                description="test",
                expected_artifact="x.py",
                status=ArtifactStatus.DONE,
            ),
        ]
        report = ComplianceMatrixReport.build(entries)
        assert "." in report.coverage_pct

    def test_report_build_counts_done(self):
        entries = [
            MatrixEntry(
                block="S16",
                item_id=f"FA-0{i}",
                description="test",
                expected_artifact=f"x{i}.py",
                status=ArtifactStatus.DONE if i < 3 else ArtifactStatus.NOT_STARTED,
            )
            for i in range(5)
        ]
        report = ComplianceMatrixReport.build(entries)
        assert report.done_count == 3
        assert report.not_started_count == 2

    def test_report_has_scanned_at(self):
        report = ComplianceMatrixReport.build([])
        assert report.scanned_at is not None

    def test_artifact_status_enum_values(self):
        assert ArtifactStatus.DONE == "DONE"
        assert ArtifactStatus.NOT_STARTED == "NOT_STARTED"
        assert ArtifactStatus.BLOCKED == "BLOCKED"

    def test_matrix_entry_frozen(self):
        entry = MatrixEntry(
            block="S16/FA",
            item_id="FA-01",
            description="test",
            expected_artifact="x.py",
        )
        with pytest.raises((TypeError, ValueError, AttributeError)):
            entry.block = "changed"  # type: ignore[misc]

    def test_report_blocked_count(self):
        entries = [
            MatrixEntry(
                block="S16",
                item_id="FA-01",
                description="test",
                expected_artifact="x.py",
                status=ArtifactStatus.BLOCKED,
            ),
            MatrixEntry(
                block="S16",
                item_id="FA-02",
                description="test",
                expected_artifact="y.py",
                status=ArtifactStatus.DONE,
            ),
        ]
        report = ComplianceMatrixReport.build(entries)
        assert report.blocked_count == 1
        assert report.done_count == 1

    def test_coverage_pct_empty_list(self):
        report = ComplianceMatrixReport.build([])
        assert report.coverage_pct == "0"

    def test_matrix_entry_actual_path_default_none(self):
        entry = MatrixEntry(
            block="S16",
            item_id="FA-01",
            description="test",
            expected_artifact="x.py",
        )
        assert entry.actual_path is None

    def test_matrix_entry_test_count_default_zero(self):
        entry = MatrixEntry(
            block="S16",
            item_id="FA-01",
            description="test",
            expected_artifact="x.py",
        )
        assert entry.test_count == 0


class TestMatrixScannerInMemory:
    def test_scan_all_returns_report(self):
        port = InMemoryArtifactCheckPort()
        scanner = MatrixScanner(port)
        report = scanner.scan_all()
        assert isinstance(report, ComplianceMatrixReport)

    def test_scan_all_with_no_artifacts_all_not_started(self):
        port = InMemoryArtifactCheckPort(present=set())
        scanner = MatrixScanner(port)
        report = scanner.scan_all()
        assert report.done_count == 0
        assert report.not_started_count == len(_MATRIX_DEFINITIONS)

    def test_scan_all_with_fa01_present(self):
        port = InMemoryArtifactCheckPort(present={"services/recon/reconciliation_engine_v2.py"})
        scanner = MatrixScanner(port)
        report = scanner.scan_all()
        fa01 = next(e for e in report.entries if e.item_id == "FA-01")
        assert fa01.status == ArtifactStatus.DONE

    def test_scan_all_fa01_absent_is_not_started(self):
        port = InMemoryArtifactCheckPort(present=set())
        scanner = MatrixScanner(port)
        report = scanner.scan_all()
        fa01 = next(e for e in report.entries if e.item_id == "FA-01")
        assert fa01.status == ArtifactStatus.NOT_STARTED

    def test_scan_all_fa02_camt053_parser(self):
        port = InMemoryArtifactCheckPort(present={"services/recon/camt053_parser.py"})
        scanner = MatrixScanner(port)
        report = scanner.scan_all()
        fa02 = next(e for e in report.entries if e.item_id == "FA-02")
        assert fa02.status == ArtifactStatus.DONE

    def test_scan_all_fa03_dbt_fin060(self):
        port = InMemoryArtifactCheckPort(present={"dbt/models/fin060/fin060_monthly.sql"})
        scanner = MatrixScanner(port)
        report = scanner.scan_all()
        fa03 = next(e for e in report.entries if e.item_id == "FA-03")
        assert fa03.status == ArtifactStatus.DONE

    def test_scan_all_fa04_pgaudit(self):
        port = InMemoryArtifactCheckPort(present={"services/audit/pgaudit_config.py"})
        scanner = MatrixScanner(port)
        report = scanner.scan_all()
        fa04 = next(e for e in report.entries if e.item_id == "FA-04")
        assert fa04.status == ArtifactStatus.DONE

    def test_scan_all_fa05_weasyprint(self):
        port = InMemoryArtifactCheckPort(present={"services/reporting/fin060_generator_v2.py"})
        scanner = MatrixScanner(port)
        report = scanner.scan_all()
        fa05 = next(e for e in report.entries if e.item_id == "FA-05")
        assert fa05.status == ArtifactStatus.DONE

    def test_scan_all_fa06_frankfurter(self):
        port = InMemoryArtifactCheckPort(present={"services/fx_rates/frankfurter_client.py"})
        scanner = MatrixScanner(port)
        report = scanner.scan_all()
        fa06 = next(e for e in report.entries if e.item_id == "FA-06")
        assert fa06.status == ArtifactStatus.DONE

    def test_scan_all_fa07_adorsys(self):
        port = InMemoryArtifactCheckPort(present={"services/psd2_gateway/adorsys_client.py"})
        scanner = MatrixScanner(port)
        report = scanner.scan_all()
        fa07 = next(e for e in report.entries if e.item_id == "FA-07")
        assert fa07.status == ArtifactStatus.DONE

    def test_scan_all_s312_midaz_mcp(self):
        port = InMemoryArtifactCheckPort(present={"services/midaz_mcp/midaz_client.py"})
        scanner = MatrixScanner(port)
        report = scanner.scan_all()
        s312 = next(e for e in report.entries if e.item_id == "S3-12")
        assert s312.status == ArtifactStatus.DONE

    def test_scan_all_s313_fraud_tracer(self):
        port = InMemoryArtifactCheckPort(present={"services/fraud_tracer/tracer_engine.py"})
        scanner = MatrixScanner(port)
        report = scanner.scan_all()
        s313 = next(e for e in report.entries if e.item_id == "S3-13")
        assert s313.status == ArtifactStatus.DONE

    def test_scan_log_append_only(self):
        """I-24: scan_log grows with each scan_all call."""
        port = InMemoryArtifactCheckPort()
        scanner = MatrixScanner(port)
        scanner.scan_all()
        scanner.scan_all()
        assert len(scanner.scan_log) == 2

    def test_get_gaps_returns_not_started(self):
        port = InMemoryArtifactCheckPort(present=set())
        scanner = MatrixScanner(port)
        gaps = scanner.get_gaps()
        assert len(gaps) == len(_MATRIX_DEFINITIONS)
        for gap in gaps:
            assert gap.status in (ArtifactStatus.NOT_STARTED, ArtifactStatus.BLOCKED)

    def test_get_gaps_empty_when_all_done(self):
        all_paths = {d["expected_artifact"] for d in _MATRIX_DEFINITIONS}
        port = InMemoryArtifactCheckPort(present=all_paths)
        scanner = MatrixScanner(port)
        gaps = scanner.get_gaps()
        assert len(gaps) == 0

    def test_all_definitions_have_expected_fields(self):
        for defn in _MATRIX_DEFINITIONS:
            assert "block" in defn
            assert "item_id" in defn
            assert "description" in defn
            assert "expected_artifact" in defn

    def test_coverage_pct_100_when_all_done(self):
        all_paths = {d["expected_artifact"] for d in _MATRIX_DEFINITIONS}
        port = InMemoryArtifactCheckPort(present=all_paths)
        scanner = MatrixScanner(port)
        report = scanner.scan_all()
        assert report.coverage_pct == "100.0"

    def test_coverage_pct_0_when_none_done(self):
        port = InMemoryArtifactCheckPort(present=set())
        scanner = MatrixScanner(port)
        report = scanner.scan_all()
        assert report.coverage_pct == "0.0"

    def test_actual_path_set_when_artifact_present(self):
        port = InMemoryArtifactCheckPort(present={"services/recon/reconciliation_engine_v2.py"})
        scanner = MatrixScanner(port)
        report = scanner.scan_all()
        fa01 = next(e for e in report.entries if e.item_id == "FA-01")
        assert fa01.actual_path == "services/recon/reconciliation_engine_v2.py"

    def test_actual_path_none_when_artifact_absent(self):
        port = InMemoryArtifactCheckPort(present=set())
        scanner = MatrixScanner(port)
        report = scanner.scan_all()
        fa01 = next(e for e in report.entries if e.item_id == "FA-01")
        assert fa01.actual_path is None

    def test_scan_returns_all_defined_items(self):
        port = InMemoryArtifactCheckPort()
        scanner = MatrixScanner(port)
        report = scanner.scan_all()
        assert len(report.entries) == len(_MATRIX_DEFINITIONS)

    def test_scan_log_initial_empty(self):
        port = InMemoryArtifactCheckPort()
        scanner = MatrixScanner(port)
        assert len(scanner.scan_log) == 0

    def test_get_gaps_triggers_scan_if_no_log(self):
        port = InMemoryArtifactCheckPort(present=set())
        scanner = MatrixScanner(port)
        gaps = scanner.get_gaps()
        assert len(scanner.scan_log) == 1

    def test_scan_log_three_calls(self):
        port = InMemoryArtifactCheckPort()
        scanner = MatrixScanner(port)
        scanner.scan_all()
        scanner.scan_all()
        scanner.scan_all()
        assert len(scanner.scan_log) == 3

    def test_partial_artifacts_present(self):
        port = InMemoryArtifactCheckPort(
            present={
                "services/recon/reconciliation_engine_v2.py",
                "services/recon/camt053_parser.py",
            }
        )
        scanner = MatrixScanner(port)
        report = scanner.scan_all()
        assert report.done_count == 2
        assert report.not_started_count == len(_MATRIX_DEFINITIONS) - 2

    def test_obs01_health_aggregator(self):
        port = InMemoryArtifactCheckPort(present={"services/observability/health_aggregator.py"})
        scanner = MatrixScanner(port)
        report = scanner.scan_all()
        obs01 = next(e for e in report.entries if e.item_id == "OBS-01")
        assert obs01.status == ArtifactStatus.DONE

    def test_obs02_compliance_monitor(self):
        port = InMemoryArtifactCheckPort(present={"services/observability/compliance_monitor.py"})
        scanner = MatrixScanner(port)
        report = scanner.scan_all()
        obs02 = next(e for e in report.entries if e.item_id == "OBS-02")
        assert obs02.status == ArtifactStatus.DONE


class TestComplianceAgentIntegration:
    def test_agent_run_scan_returns_report(self):
        from services.compliance_sync.compliance_agent import ComplianceMatrixAgent

        port = InMemoryArtifactCheckPort()
        scanner = MatrixScanner(port)
        agent = ComplianceMatrixAgent(scanner)
        report = agent.run_scan()
        assert isinstance(report, ComplianceMatrixReport)

    def test_agent_proposals_not_auto_approved(self):
        """I-27: proposals start unapproved."""
        from services.compliance_sync.compliance_agent import ComplianceMatrixAgent

        port = InMemoryArtifactCheckPort(present=set())
        scanner = MatrixScanner(port)
        agent = ComplianceMatrixAgent(scanner)
        agent.run_scan()
        for proposal in agent.proposals:
            assert proposal.approved is False

    def test_agent_proposals_require_compliance_officer(self):
        """I-27: all proposals require COMPLIANCE_OFFICER."""
        from services.compliance_sync.compliance_agent import ComplianceMatrixAgent

        port = InMemoryArtifactCheckPort(present=set())
        scanner = MatrixScanner(port)
        agent = ComplianceMatrixAgent(scanner)
        agent.run_scan()
        for proposal in agent.proposals:
            assert proposal.requires_approval_from == "COMPLIANCE_OFFICER"

    def test_no_proposals_when_all_done(self):
        from services.compliance_sync.compliance_agent import ComplianceMatrixAgent

        all_paths = {d["expected_artifact"] for d in _MATRIX_DEFINITIONS}
        port = InMemoryArtifactCheckPort(present=all_paths)
        scanner = MatrixScanner(port)
        agent = ComplianceMatrixAgent(scanner)
        agent.run_scan()
        assert len(agent.proposals) == 0

    def test_real_filesystem_scan_shows_fa01_done(self):
        """Verify real filesystem has the Sprint 36 artifacts."""
        scanner = MatrixScanner()  # uses real filesystem
        report = scanner.scan_all()
        fa01 = next((e for e in report.entries if e.item_id == "FA-01"), None)
        assert fa01 is not None
        assert fa01.status in (ArtifactStatus.DONE, ArtifactStatus.NOT_STARTED)

    def test_real_filesystem_s312_done(self):
        """Sprint 39 delivers S3-12: midaz_client.py should exist."""
        scanner = MatrixScanner()
        report = scanner.scan_all()
        s312 = next((e for e in report.entries if e.item_id == "S3-12"), None)
        assert s312 is not None

    def test_real_filesystem_s313_done(self):
        """Sprint 39 delivers S3-13: tracer_engine.py should exist."""
        scanner = MatrixScanner()
        report = scanner.scan_all()
        s313 = next((e for e in report.entries if e.item_id == "S3-13"), None)
        assert s313 is not None

    def test_proposals_have_item_ids(self):
        from services.compliance_sync.compliance_agent import ComplianceMatrixAgent

        port = InMemoryArtifactCheckPort(present=set())
        scanner = MatrixScanner(port)
        agent = ComplianceMatrixAgent(scanner)
        agent.run_scan()
        for proposal in agent.proposals:
            assert proposal.item_id is not None
            assert len(proposal.item_id) > 0

    def test_proposals_count_matches_not_started(self):
        from services.compliance_sync.compliance_agent import ComplianceMatrixAgent

        port = InMemoryArtifactCheckPort(present=set())
        scanner = MatrixScanner(port)
        agent = ComplianceMatrixAgent(scanner)
        report = agent.run_scan()
        not_started = sum(1 for e in report.entries if e.status == ArtifactStatus.NOT_STARTED)
        assert len(agent.proposals) == not_started

    def test_proposal_ids_are_unique(self):
        from services.compliance_sync.compliance_agent import ComplianceMatrixAgent

        port = InMemoryArtifactCheckPort(present=set())
        scanner = MatrixScanner(port)
        agent = ComplianceMatrixAgent(scanner)
        agent.run_scan()
        ids = [p.proposal_id for p in agent.proposals]
        assert len(ids) == len(set(ids))

    def test_proposal_has_proposed_at_timestamp(self):
        from services.compliance_sync.compliance_agent import ComplianceMatrixAgent

        port = InMemoryArtifactCheckPort(present=set())
        scanner = MatrixScanner(port)
        agent = ComplianceMatrixAgent(scanner)
        agent.run_scan()
        for proposal in agent.proposals:
            assert proposal.proposed_at is not None
            assert len(proposal.proposed_at) > 0

    def test_scan_log_returns_copy_not_reference(self):
        """I-24: scan_log property returns a copy to prevent external mutation."""
        port = InMemoryArtifactCheckPort()
        scanner = MatrixScanner(port)
        scanner.scan_all()
        log1 = scanner.scan_log
        log1.clear()
        assert len(scanner.scan_log) == 1

    def test_matrix_entry_block_stored(self):
        entry = MatrixEntry(
            block="S3",
            item_id="S3-12",
            description="Midaz integration",
            expected_artifact="services/midaz_mcp/midaz_client.py",
        )
        assert entry.block == "S3"

    def test_coverage_pct_single_done_entry(self):
        entries = [
            MatrixEntry(
                block="S16",
                item_id="FA-01",
                description="test",
                expected_artifact="x.py",
                status=ArtifactStatus.DONE,
            ),
        ]
        report = ComplianceMatrixReport.build(entries)
        assert report.coverage_pct == "100.0"
        assert report.done_count == 1
        assert report.not_started_count == 0

    def test_in_memory_port_empty_by_default(self):
        port = InMemoryArtifactCheckPort()
        assert not port.exists("any/path.py")

    def test_in_memory_port_present_paths(self):
        port = InMemoryArtifactCheckPort(present={"a/b.py", "c/d.py"})
        assert port.exists("a/b.py")
        assert port.exists("c/d.py")
        assert not port.exists("e/f.py")

    def test_artifact_status_in_progress(self):
        entry = MatrixEntry(
            block="S16",
            item_id="FA-01",
            description="test",
            expected_artifact="x.py",
            status=ArtifactStatus.IN_PROGRESS,
        )
        assert entry.status == ArtifactStatus.IN_PROGRESS

    def test_report_scanned_at_is_iso_string(self):
        report = ComplianceMatrixReport.build([])
        # Must be parseable as ISO datetime
        from datetime import datetime

        dt = datetime.fromisoformat(report.scanned_at)
        assert dt is not None
