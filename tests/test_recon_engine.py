"""
tests/test_recon_engine.py
Tests for ReconciliationEngine — FCA CASS 7 daily recon (IL-SAF-01).

Acceptance criteria:
- test_daily_recon_balanced (Decimal, I-01)
- test_daily_recon_discrepancy_detected (I-27 HITL)
- test_recon_audit_trail (I-24)
- test_recon_blocked_jurisdiction_excluded (I-02)
- test_recon_report_generated
- test_recon_large_value_flagged (>£50k, I-04)
"""

from decimal import Decimal
import json

import pytest

from services.recon.recon_engine import (
    HITLEscalation,
    InMemoryReconAuditPort,
    ReconciliationEngine,
)
from services.recon.recon_models import (
    BLOCKED_JURISDICTIONS,
    LARGE_VALUE_THRESHOLD,
    RECON_TOLERANCE,
    AccountBalance,
    Discrepancy,
    DiscrepancyType,
    EscalationLevel,
    ReconAuditEntry,
    ReconResult,
    ReconStatus,
)
from services.recon.recon_port import InMemoryLedgerPort
from services.recon.recon_report import ReconReport, ReconReportGenerator

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def ledger():
    return InMemoryLedgerPort()


@pytest.fixture
def audit():
    return InMemoryReconAuditPort()


@pytest.fixture
def engine(ledger, audit):
    return ReconciliationEngine(ledger=ledger, audit=audit)


@pytest.fixture
def report_gen():
    return ReconReportGenerator()


# ── Daily Recon Balanced Tests ───────────────────────────────────────────────


class TestDailyReconBalanced:
    def test_daily_recon_balanced(self, engine, ledger):
        """AC: client funds == safeguarding → BALANCED (Decimal, I-01)."""
        ledger.add_client_fund("cf-001", Decimal("100000.00"))
        ledger.add_safeguarding("sg-001", Decimal("100000.00"))

        result = engine.run_daily_recon("2026-04-28")

        assert result.status == ReconStatus.BALANCED
        assert isinstance(result.client_funds_total, Decimal)
        assert isinstance(result.safeguarding_total, Decimal)
        assert result.client_funds_total == Decimal("100000.00")
        assert result.safeguarding_total == Decimal("100000.00")
        assert result.difference == Decimal("0")
        assert len(result.discrepancies) == 0

    def test_balanced_within_tolerance(self, engine, ledger):
        """Difference within tolerance (£0.01) is still BALANCED."""
        ledger.add_client_fund("cf-001", Decimal("100000.00"))
        ledger.add_safeguarding("sg-001", Decimal("100000.01"))

        result = engine.run_daily_recon("2026-04-28")
        assert result.status == ReconStatus.BALANCED

    def test_balanced_multiple_accounts(self, engine, ledger):
        """Multiple accounts summed correctly."""
        ledger.add_client_fund("cf-001", Decimal("50000.00"))
        ledger.add_client_fund("cf-002", Decimal("50000.00"))
        ledger.add_safeguarding("sg-001", Decimal("70000.00"))
        ledger.add_safeguarding("sg-002", Decimal("30000.00"))

        result = engine.run_daily_recon("2026-04-28")
        assert result.status == ReconStatus.BALANCED
        assert result.client_funds_total == Decimal("100000.00")
        assert result.safeguarding_total == Decimal("100000.00")

    def test_empty_accounts_balanced(self, engine):
        """No accounts → BALANCED (both zero)."""
        result = engine.run_daily_recon("2026-04-28")
        assert result.status == ReconStatus.BALANCED
        assert result.client_funds_total == Decimal("0")
        assert result.safeguarding_total == Decimal("0")


# ── Discrepancy Detection Tests ──────────────────────────────────────────────


class TestDiscrepancyDetection:
    def test_daily_recon_discrepancy_detected_shortfall(self, engine, ledger):
        """AC: shortfall detected → DISCREPANCY + HITL escalation (I-27)."""
        ledger.add_client_fund("cf-001", Decimal("100000.00"))
        ledger.add_safeguarding("sg-001", Decimal("95000.00"))

        result = engine.run_daily_recon("2026-04-28")

        assert result.status == ReconStatus.DISCREPANCY
        assert len(result.discrepancies) == 1
        disc = result.discrepancies[0]
        assert disc.discrepancy_type == DiscrepancyType.SHORTFALL
        assert disc.difference == Decimal("5000.00")
        assert disc.escalation_level == EscalationLevel.ALERT

    def test_discrepancy_surplus(self, engine, ledger):
        """Surplus (safeguarding > client) also flagged."""
        ledger.add_client_fund("cf-001", Decimal("90000.00"))
        ledger.add_safeguarding("sg-001", Decimal("95000.00"))

        result = engine.run_daily_recon("2026-04-28")
        assert result.status == ReconStatus.DISCREPANCY
        disc = result.discrepancies[0]
        assert disc.discrepancy_type == DiscrepancyType.SURPLUS

    def test_shortfall_triggers_hitl_escalation(self, engine, ledger):
        """AC: shortfall triggers HITL escalation with MLRO approval (I-27)."""
        ledger.add_client_fund("cf-001", Decimal("100000.00"))
        ledger.add_safeguarding("sg-001", Decimal("95000.00"))

        engine.run_daily_recon("2026-04-28")

        assert len(engine.escalations) == 1
        esc = engine.escalations[0]
        assert isinstance(esc, HITLEscalation)
        assert esc.requires_approval_from == "MLRO"

    def test_surplus_no_hitl_escalation(self, engine, ledger):
        """Surplus does NOT trigger HITL escalation."""
        ledger.add_client_fund("cf-001", Decimal("90000.00"))
        ledger.add_safeguarding("sg-001", Decimal("95000.00"))

        engine.run_daily_recon("2026-04-28")
        assert len(engine.escalations) == 0

    def test_large_discrepancy_mlro_escalation(self, engine, ledger):
        """Large shortfall (>£50k) escalates to HITL_MLRO level."""
        ledger.add_client_fund("cf-001", Decimal("200000.00"))
        ledger.add_safeguarding("sg-001", Decimal("100000.00"))

        result = engine.run_daily_recon("2026-04-28")
        disc = result.discrepancies[0]
        assert disc.escalation_level == EscalationLevel.HITL_MLRO

    def test_exact_tolerance_boundary(self, engine, ledger):
        """Difference exactly at tolerance → BALANCED."""
        ledger.add_client_fund("cf-001", Decimal("100000.00"))
        ledger.add_safeguarding("sg-001", Decimal("99999.99"))

        result = engine.run_daily_recon("2026-04-28")
        assert result.status == ReconStatus.BALANCED

    def test_just_above_tolerance(self, engine, ledger):
        """Difference just above tolerance → DISCREPANCY."""
        ledger.add_client_fund("cf-001", Decimal("100000.00"))
        ledger.add_safeguarding("sg-001", Decimal("99999.98"))

        result = engine.run_daily_recon("2026-04-28")
        assert result.status == ReconStatus.DISCREPANCY


# ── Audit Trail Tests ────────────────────────────────────────────────────────


class TestAuditTrail:
    def test_recon_audit_trail(self, engine, ledger, audit):
        """AC: immutable audit entry recorded per reconciliation (I-24)."""
        ledger.add_client_fund("cf-001", Decimal("100000.00"))
        ledger.add_safeguarding("sg-001", Decimal("100000.00"))

        result = engine.run_daily_recon("2026-04-28")

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.recon_id == result.recon_id
        assert entry.action == "DAILY_RECON"
        assert entry.status == ReconStatus.BALANCED
        assert isinstance(entry.client_funds_total, Decimal)
        assert isinstance(entry.safeguarding_total, Decimal)
        assert entry.actor == "SYSTEM"

    def test_audit_entry_immutable(self):
        """ReconAuditEntry is frozen (I-24)."""
        entry = ReconAuditEntry(
            recon_id="r-001",
            action="TEST",
            status=ReconStatus.BALANCED,
            client_funds_total=Decimal("100"),
            safeguarding_total=Decimal("100"),
            actor="test",
        )
        with pytest.raises(AttributeError):
            entry.action = "MODIFIED"  # type: ignore[misc]

    def test_multiple_recons_produce_multiple_audit_entries(self, engine, ledger, audit):
        """Each recon run produces its own audit entry."""
        ledger.add_client_fund("cf-001", Decimal("100.00"))
        ledger.add_safeguarding("sg-001", Decimal("100.00"))

        engine.run_daily_recon("2026-04-28")
        engine.run_daily_recon("2026-04-29")

        assert len(audit.entries) == 2

    def test_audit_records_discrepancy_details(self, engine, ledger, audit):
        """Audit entry includes discrepancy count in details."""
        ledger.add_client_fund("cf-001", Decimal("100000.00"))
        ledger.add_safeguarding("sg-001", Decimal("90000.00"))

        engine.run_daily_recon("2026-04-28")
        entry = audit.entries[0]
        assert "discrepancies=1" in entry.details


# ── Blocked Jurisdiction Tests ─────────────────────────────────────��─────────


class TestBlockedJurisdictions:
    def test_recon_blocked_jurisdiction_excluded(self, engine, ledger):
        """AC: blocked jurisdiction accounts excluded from recon (I-02)."""
        ledger.add_client_fund("cf-gb", Decimal("100000.00"), jurisdiction="GB")
        ledger.add_client_fund("cf-ru", Decimal("50000.00"), jurisdiction="RU")
        ledger.add_safeguarding("sg-001", Decimal("100000.00"), jurisdiction="GB")

        result = engine.run_daily_recon("2026-04-28")

        assert result.status == ReconStatus.BALANCED
        assert result.client_funds_total == Decimal("100000.00")  # RU excluded
        assert "RU" in result.excluded_jurisdictions

    def test_multiple_blocked_jurisdictions(self, engine, ledger):
        """Multiple blocked jurisdictions excluded."""
        ledger.add_client_fund("cf-gb", Decimal("100.00"), jurisdiction="GB")
        ledger.add_client_fund("cf-ir", Decimal("200.00"), jurisdiction="IR")
        ledger.add_client_fund("cf-kp", Decimal("300.00"), jurisdiction="KP")
        ledger.add_safeguarding("sg-001", Decimal("100.00"), jurisdiction="GB")

        result = engine.run_daily_recon("2026-04-28")
        assert result.status == ReconStatus.BALANCED
        assert "IR" in result.excluded_jurisdictions
        assert "KP" in result.excluded_jurisdictions

    def test_blocked_jurisdiction_case_insensitive(self, engine, ledger):
        """Jurisdiction check is case-insensitive."""
        ledger.add_client_fund("cf-gb", Decimal("100.00"), jurisdiction="GB")
        ledger.add_client_fund("cf-ru", Decimal("500.00"), jurisdiction="ru")
        ledger.add_safeguarding("sg-001", Decimal("100.00"))

        result = engine.run_daily_recon("2026-04-28")
        assert result.client_funds_total == Decimal("100.00")

    def test_all_blocked_countries(self):
        """Verify all I-02 blocked countries are in the set."""
        expected = {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}
        assert expected == BLOCKED_JURISDICTIONS


# ── Large Value Tests ────────────────────────────────────────────────────────


class TestLargeValues:
    def test_recon_large_value_flagged(self, engine, ledger):
        """AC: accounts with balance >= £50k flagged (I-04)."""
        ledger.add_client_fund("cf-001", Decimal("60000.00"))
        ledger.add_safeguarding("sg-001", Decimal("60000.00"))

        result = engine.run_daily_recon("2026-04-28")
        assert result.large_values_flagged == 2  # Both flagged

    def test_below_large_value_not_flagged(self, engine, ledger):
        """Accounts below £50k threshold not flagged."""
        ledger.add_client_fund("cf-001", Decimal("49999.99"))
        ledger.add_safeguarding("sg-001", Decimal("49999.99"))

        result = engine.run_daily_recon("2026-04-28")
        assert result.large_values_flagged == 0

    def test_exactly_at_threshold_flagged(self, engine, ledger):
        """Account exactly at £50k is flagged."""
        ledger.add_client_fund("cf-001", Decimal("50000.00"))
        ledger.add_safeguarding("sg-001", Decimal("50000.00"))

        result = engine.run_daily_recon("2026-04-28")
        assert result.large_values_flagged == 2

    def test_mixed_large_and_small(self, engine, ledger):
        """Only large accounts flagged, small ones not."""
        ledger.add_client_fund("cf-001", Decimal("60000.00"))
        ledger.add_client_fund("cf-002", Decimal("1000.00"))
        ledger.add_safeguarding("sg-001", Decimal("61000.00"))

        result = engine.run_daily_recon("2026-04-28")
        assert result.large_values_flagged == 2  # cf-001 + sg-001


# ── Report Generator Tests ───────────────────────────────────────────────────


class TestReconReport:
    def test_recon_report_generated(self, engine, ledger, report_gen):
        """AC: daily report generated from ReconResult."""
        ledger.add_client_fund("cf-001", Decimal("100000.00"))
        ledger.add_safeguarding("sg-001", Decimal("100000.00"))

        result = engine.run_daily_recon("2026-04-28")
        report = report_gen.generate(result)

        assert isinstance(report, ReconReport)
        assert report.recon_id == result.recon_id
        assert report.status == "BALANCED"
        assert report.client_funds_total == "100000.00"
        assert report.safeguarding_total == "100000.00"
        assert report.report_format == "JSON"

    def test_report_to_json(self, engine, ledger, report_gen):
        """Report serializable to valid JSON."""
        ledger.add_client_fund("cf-001", Decimal("100000.00"))
        ledger.add_safeguarding("sg-001", Decimal("100000.00"))

        result = engine.run_daily_recon("2026-04-28")
        report = report_gen.generate(result)
        json_str = report_gen.to_json(report)

        data = json.loads(json_str)
        assert data["status"] == "BALANCED"
        assert data["fca_compliance"]["regulation"] == "FCA CASS 7"
        assert data["fca_compliance"]["balanced"] is True

    def test_report_discrepancy_json(self, engine, ledger, report_gen):
        """Discrepancy report has balanced=False."""
        ledger.add_client_fund("cf-001", Decimal("100000.00"))
        ledger.add_safeguarding("sg-001", Decimal("90000.00"))

        result = engine.run_daily_recon("2026-04-28")
        report = report_gen.generate(result)
        json_str = report_gen.to_json(report)

        data = json.loads(json_str)
        assert data["fca_compliance"]["balanced"] is False
        assert data["discrepancy_count"] == 1

    def test_report_immutable(self, engine, ledger, report_gen):
        """ReconReport is frozen."""
        ledger.add_client_fund("cf-001", Decimal("100.00"))
        ledger.add_safeguarding("sg-001", Decimal("100.00"))

        result = engine.run_daily_recon("2026-04-28")
        report = report_gen.generate(result)
        with pytest.raises(AttributeError):
            report.status = "MODIFIED"  # type: ignore[misc]

    def test_reports_stored(self, engine, ledger, report_gen):
        """Generator stores all generated reports."""
        ledger.add_client_fund("cf-001", Decimal("100.00"))
        ledger.add_safeguarding("sg-001", Decimal("100.00"))

        r1 = engine.run_daily_recon("2026-04-28")
        r2 = engine.run_daily_recon("2026-04-29")
        report_gen.generate(r1)
        report_gen.generate(r2)

        assert len(report_gen.reports) == 2


# ─�� Model Tests ──────────────────────────────────────────────────────────────


class TestModels:
    def test_account_balance_decimal_only(self):
        """AccountBalance rejects non-Decimal (I-01)."""
        with pytest.raises(TypeError, match="Decimal"):
            AccountBalance(
                account_id="a-001",
                account_name="Test",
                balance=100.0,  # type: ignore[arg-type]
                currency="GBP",
            )

    def test_discrepancy_decimal_only(self):
        """Discrepancy rejects non-Decimal fields (I-01)."""
        with pytest.raises(TypeError, match="Decimal"):
            Discrepancy(
                discrepancy_id="d-001",
                discrepancy_type=DiscrepancyType.SHORTFALL,
                expected=100.0,  # type: ignore[arg-type]
                actual=Decimal("90"),
                difference=Decimal("10"),
                account_id="a-001",
                description="test",
            )

    def test_recon_result_decimal_only(self):
        """ReconResult rejects non-Decimal fields (I-01)."""
        with pytest.raises(TypeError, match="Decimal"):
            ReconResult(
                recon_id="r-001",
                recon_date="2026-04-28",
                status=ReconStatus.BALANCED,
                client_funds_total=100.0,  # type: ignore[arg-type]
                safeguarding_total=Decimal("100"),
                difference=Decimal("0"),
            )

    def test_recon_result_frozen(self):
        """ReconResult is immutable (I-24)."""
        result = ReconResult(
            recon_id="r-001",
            recon_date="2026-04-28",
            status=ReconStatus.BALANCED,
            client_funds_total=Decimal("100"),
            safeguarding_total=Decimal("100"),
            difference=Decimal("0"),
        )
        with pytest.raises(AttributeError):
            result.status = ReconStatus.DISCREPANCY  # type: ignore[misc]

    def test_recon_tolerance_value(self):
        """RECON_TOLERANCE is £0.01."""
        assert Decimal("0.01") == RECON_TOLERANCE

    def test_large_value_threshold(self):
        """LARGE_VALUE_THRESHOLD is £50,000."""
        assert Decimal("50000") == LARGE_VALUE_THRESHOLD
