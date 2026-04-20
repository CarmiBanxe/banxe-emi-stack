"""Tests for ComplianceReporter — Phase 46 (IL-SRS-01)."""

from __future__ import annotations

import hashlib
import json

from services.sanctions_screening.compliance_reporter import ComplianceReporter
from services.sanctions_screening.models import (
    HITLProposal,
    InMemoryAlertStore,
    InMemoryScreeningStore,
)


def make_reporter():
    return ComplianceReporter(InMemoryScreeningStore(), InMemoryAlertStore())


# --- generate_sar (I-27: ALWAYS HITL) ---


def test_generate_sar_returns_hitl():
    reporter = make_reporter()
    result = reporter.generate_sar("req_001", "mlro_ref_001", "compliance_officer")
    assert isinstance(result, HITLProposal)


def test_generate_sar_requires_mlro():
    reporter = make_reporter()
    result = reporter.generate_sar("req_001", "mlro_ref_001", "officer")
    assert result.requires_approval_from == "MLRO"


def test_generate_sar_reason_poca_2002():
    reporter = make_reporter()
    result = reporter.generate_sar("req_001", "mlro_ref_001", "officer")
    assert "POCA 2002" in result.reason or "SAR" in result.reason


def test_generate_sar_autonomy_l4():
    reporter = make_reporter()
    result = reporter.generate_sar("req_001", "mlro_ref", "officer")
    assert result.autonomy_level == "L4"


# --- generate_ofsi_report ---


def test_generate_ofsi_report_returns_dict():
    reporter = make_reporter()
    result = reporter.generate_ofsi_report("alert_001")
    assert isinstance(result, dict)
    assert result["alert_id"] == "alert_001"


def test_generate_ofsi_report_has_reg_ref():
    reporter = make_reporter()
    result = reporter.generate_ofsi_report("alert_001")
    assert "OFSI" in result.get("regulatory_ref", "")


# --- get_screening_stats ---


def test_get_screening_stats_fields():
    reporter = make_reporter()
    stats = reporter.get_screening_stats("daily")
    assert "period" in stats
    assert "total" in stats
    assert "clear" in stats
    assert "possible_match" in stats
    assert "confirmed_match" in stats


def test_get_screening_stats_period_daily():
    reporter = make_reporter()
    stats = reporter.get_screening_stats("daily")
    assert stats["period"] == "daily"


def test_get_screening_stats_period_weekly():
    reporter = make_reporter()
    stats = reporter.get_screening_stats("weekly")
    assert stats["period"] == "weekly"


# --- export_audit_trail (I-12: SHA-256) ---


def test_export_audit_trail_has_checksum():
    reporter = make_reporter()
    result = reporter.export_audit_trail("Ivan Petrov")
    assert "checksum" in result


def test_export_audit_trail_checksum_is_sha256():
    reporter = make_reporter()
    result = reporter.export_audit_trail("Ivan Petrov")
    assert len(result["checksum"]) == 64  # SHA-256 hex = 64 chars


def test_export_audit_trail_checksum_consistent():
    reporter = make_reporter()
    result = reporter.export_audit_trail("Ivan Petrov")
    # Re-compute checksum manually
    data = {k: v for k, v in result.items() if k != "checksum"}
    serialised = json.dumps(data, sort_keys=True).encode()
    expected = hashlib.sha256(serialised).hexdigest()
    assert result["checksum"] == expected


def test_export_audit_trail_entity_name():
    reporter = make_reporter()
    result = reporter.export_audit_trail("Test Entity")
    assert result["entity_name"] == "Test Entity"


# --- generate_board_summary (I-27) ---


def test_generate_board_summary_returns_hitl():
    reporter = make_reporter()
    result = reporter.generate_board_summary("Q1-2026")
    assert isinstance(result, HITLProposal)


def test_generate_board_summary_requires_mlro():
    reporter = make_reporter()
    result = reporter.generate_board_summary("Q1-2026")
    assert result.requires_approval_from == "MLRO"
