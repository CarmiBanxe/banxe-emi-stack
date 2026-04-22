"""Tests for ComplianceMonitor (IL-OBS-01)."""

from __future__ import annotations

from services.observability.compliance_monitor import (
    ComplianceFlag,
    ComplianceMonitor,
    InMemoryComplianceCheckPort,
)


class TestComplianceMonitorAllCompliant:
    def test_all_compliant_returns_compliant(self):
        mon = ComplianceMonitor(InMemoryComplianceCheckPort())
        report = mon.scan()
        assert report.overall_flag == ComplianceFlag.COMPLIANT

    def test_zero_violations_when_all_pass(self):
        mon = ComplianceMonitor(InMemoryComplianceCheckPort())
        report = mon.scan()
        assert report.violation_count == 0

    def test_i01_check_present(self):
        mon = ComplianceMonitor(InMemoryComplianceCheckPort())
        report = mon.scan()
        ids = [c.invariant_id for c in report.checks]
        assert "I-01" in ids

    def test_i02_check_present(self):
        mon = ComplianceMonitor(InMemoryComplianceCheckPort())
        report = mon.scan()
        ids = [c.invariant_id for c in report.checks]
        assert "I-02" in ids

    def test_i24_check_present(self):
        mon = ComplianceMonitor(InMemoryComplianceCheckPort())
        report = mon.scan()
        ids = [c.invariant_id for c in report.checks]
        assert "I-24" in ids

    def test_i27_check_present(self):
        mon = ComplianceMonitor(InMemoryComplianceCheckPort())
        report = mon.scan()
        ids = [c.invariant_id for c in report.checks]
        assert "I-27" in ids

    def test_float_violation_triggers_i01_violation(self):
        port = InMemoryComplianceCheckPort({"decimal_usage": False})
        mon = ComplianceMonitor(port)
        report = mon.scan()
        assert report.overall_flag == ComplianceFlag.VIOLATION
        i01 = next(c for c in report.checks if c.invariant_id == "I-01")
        assert i01.flag == ComplianceFlag.VIOLATION

    def test_blocked_jurisdiction_violation(self):
        port = InMemoryComplianceCheckPort({"blocked_jurisdictions": False})
        mon = ComplianceMonitor(port)
        report = mon.scan()
        assert report.overall_flag == ComplianceFlag.VIOLATION

    def test_audit_trail_violation(self):
        port = InMemoryComplianceCheckPort({"audit_trail": False})
        mon = ComplianceMonitor(port)
        report = mon.scan()
        i24 = next(c for c in report.checks if c.invariant_id == "I-24")
        assert i24.flag == ComplianceFlag.VIOLATION

    def test_hitl_gate_violation(self):
        port = InMemoryComplianceCheckPort({"hitl_gates": False})
        mon = ComplianceMonitor(port)
        report = mon.scan()
        i27 = next(c for c in report.checks if c.invariant_id == "I-27")
        assert i27.flag == ComplianceFlag.VIOLATION

    def test_report_has_scanned_at(self):
        mon = ComplianceMonitor()
        report = mon.scan()
        assert report.scanned_at is not None

    def test_multiple_violations_counted(self):
        port = InMemoryComplianceCheckPort({"decimal_usage": False, "hitl_gates": False})
        mon = ComplianceMonitor(port)
        report = mon.scan()
        assert report.violation_count == 2
