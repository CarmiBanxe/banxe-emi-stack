"""Tests for src/safeguarding/ module — CASS 15 / PS23/3.

Covers:
  DailyReconciliation — MATCHED / BREAK / PENDING
  BreachDetector      — severity escalation, streak thresholds
  FIN060Generator     — surplus/shortfall calculation, serialisation
  AuditTrail          — dry_run logging, fallback on missing httpx
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

# ---------------------------------------------------------------------------
# DailyReconciliation
# ---------------------------------------------------------------------------


class TestDailyReconciliation:
    def _recon(self, internal, external, recon_date=None):
        from src.safeguarding.daily_reconciliation import DailyReconciliation

        return DailyReconciliation(
            internal_balance_gbp=Decimal(str(internal)),
            external_balance_gbp=Decimal(str(external)) if external is not None else None,
            recon_date=recon_date or date(2026, 4, 13),
        )

    def test_matched_within_tolerance(self):
        from src.safeguarding.daily_reconciliation import ReconStatus

        result = self._recon(50000.00, 50000.005).run()
        assert result.status == ReconStatus.MATCHED
        assert result.is_compliant

    def test_matched_exact(self):
        from src.safeguarding.daily_reconciliation import ReconStatus

        result = self._recon(100000, 100000).run()
        assert result.status == ReconStatus.MATCHED

    def test_break_on_penny_diff(self):
        from src.safeguarding.daily_reconciliation import ReconStatus

        result = self._recon(50000.00, 49999.98).run()
        assert result.status == ReconStatus.BREAK
        assert not result.is_compliant
        assert result.difference_gbp == Decimal("0.02")

    def test_break_shortfall(self):
        from src.safeguarding.daily_reconciliation import ReconStatus

        result = self._recon(49000.00, 50000.00).run()
        assert result.status == ReconStatus.BREAK
        assert result.difference_gbp == Decimal("-1000.00")

    def test_pending_when_external_none(self):
        from src.safeguarding.daily_reconciliation import ReconStatus

        result = self._recon(50000.00, None).run()
        assert result.status == ReconStatus.PENDING
        assert result.external_balance_gbp is None
        assert result.difference_gbp is None

    def test_summary_matched(self):
        result = self._recon(1000, 1000).run()
        assert "MATCHED" in result.summary()

    def test_summary_break(self):
        result = self._recon(1000, 999).run()
        assert "BREAK" in result.summary()

    def test_summary_pending(self):
        result = self._recon(1000, None).run()
        assert "PENDING" in result.summary()


# ---------------------------------------------------------------------------
# BreachDetector
# ---------------------------------------------------------------------------


class TestBreachDetector:
    def _make_result(self, status_str, diff=None):
        from src.safeguarding.daily_reconciliation import ReconciliationResult, ReconStatus

        status = ReconStatus(status_str)
        return ReconciliationResult(
            recon_date=date(2026, 4, 13),
            internal_balance_gbp=Decimal("50000"),
            external_balance_gbp=Decimal("49000") if diff else Decimal("50000"),
            difference_gbp=Decimal(str(diff)) if diff is not None else None,
            status=status,
        )

    def test_no_alert_on_matched(self):
        from src.safeguarding.breach_detector import BreachDetector

        result = self._make_result("MATCHED")
        alert = BreachDetector().assess(result, consecutive_break_days=0)
        assert alert is None

    def test_minor_alert_first_break_day(self):
        from src.safeguarding.breach_detector import BreachDetector, BreachSeverity

        result = self._make_result("BREAK", diff="1.00")
        alert = BreachDetector().assess(result, consecutive_break_days=1)
        assert alert is not None
        assert alert.severity == BreachSeverity.MINOR
        assert not alert.fca_notification_required

    def test_major_alert_second_break_day(self):
        from src.safeguarding.breach_detector import BreachDetector, BreachSeverity

        result = self._make_result("BREAK", diff="1.00")
        alert = BreachDetector().assess(result, consecutive_break_days=2)
        assert alert.severity == BreachSeverity.MAJOR

    def test_critical_alert_at_streak_threshold(self):
        from src.safeguarding.breach_detector import BreachDetector, BreachSeverity

        result = self._make_result("BREAK", diff="1.00")
        alert = BreachDetector().assess(result, consecutive_break_days=3)
        assert alert.severity == BreachSeverity.CRITICAL
        assert alert.fca_notification_required

    def test_critical_on_shortfall(self):
        from src.safeguarding.breach_detector import BreachDetector, BreachSeverity

        result = self._make_result("BREAK", diff="-500.00")
        alert = BreachDetector().assess(result, consecutive_break_days=1)
        assert alert.severity == BreachSeverity.CRITICAL
        assert alert.shortfall_gbp == Decimal("500.00")
        assert alert.fca_notification_required

    def test_no_alert_on_pending_below_streak(self):
        from src.safeguarding.breach_detector import BreachDetector

        result = self._make_result("PENDING")
        alert = BreachDetector().assess(result, consecutive_break_days=2)
        assert alert is None

    def test_alert_on_pending_at_streak_threshold(self):
        from src.safeguarding.breach_detector import BreachDetector

        result = self._make_result("PENDING")
        alert = BreachDetector().assess(result, consecutive_break_days=3)
        assert alert is not None

    def test_notify_fca_dry_run_does_not_raise(self):
        from src.safeguarding.breach_detector import BreachAlert, BreachDetector, BreachSeverity

        alert = BreachAlert(
            breach_date=date(2026, 4, 13),
            severity=BreachSeverity.CRITICAL,
            consecutive_days=3,
            shortfall_gbp=None,
            description="test",
            fca_notification_required=True,
        )
        BreachDetector().notify_fca(alert, dry_run=True)  # must not raise

    def test_get_consecutive_days_trailing(self):
        from src.safeguarding.breach_detector import BreachDetector
        from src.safeguarding.daily_reconciliation import ReconciliationResult, ReconStatus

        history = [
            ReconciliationResult(
                date(2026, 4, 11),
                Decimal("1000"),
                Decimal("1000"),
                Decimal("0"),
                ReconStatus.MATCHED,
            ),
            ReconciliationResult(
                date(2026, 4, 12), Decimal("1000"), Decimal("999"), Decimal("1"), ReconStatus.BREAK
            ),
            ReconciliationResult(
                date(2026, 4, 13), Decimal("1000"), Decimal("999"), Decimal("1"), ReconStatus.BREAK
            ),
        ]
        count = BreachDetector().get_consecutive_days(history)
        assert count == 2


# ---------------------------------------------------------------------------
# FIN060Generator
# ---------------------------------------------------------------------------


class TestFIN060Generator:
    def _gen(self):
        from src.safeguarding.fin060_generator import FIN060Generator

        return FIN060Generator(
            institution_name="Banxe Ltd",
            frn="987654",
            reference_month=date(2026, 4, 1),
        )

    def test_surplus_calculation(self):
        ret = self._gen().build(
            total_client_funds_gbp=Decimal("100000"),
            safeguarding_balance_gbp=Decimal("100500"),
            num_safeguarding_accounts=1,
            safeguarding_bank="Barclays",
            daily_recon_count=22,
            daily_recon_breaks=0,
        )
        assert ret.surplus_gbp == Decimal("500")
        assert ret.shortfall_gbp == Decimal("0")
        assert ret.is_compliant

    def test_shortfall_auto_calculated(self):
        ret = self._gen().build(
            total_client_funds_gbp=Decimal("100000"),
            safeguarding_balance_gbp=Decimal("99500"),
            num_safeguarding_accounts=1,
            safeguarding_bank="Barclays",
            daily_recon_count=22,
            daily_recon_breaks=0,
        )
        assert ret.shortfall_gbp == Decimal("500")
        assert ret.surplus_gbp == Decimal("0")
        assert not ret.is_compliant

    def test_shortfall_override(self):
        ret = self._gen().build(
            total_client_funds_gbp=Decimal("100000"),
            safeguarding_balance_gbp=Decimal("99500"),
            num_safeguarding_accounts=1,
            safeguarding_bank="Barclays",
            daily_recon_count=22,
            daily_recon_breaks=0,
            shortfall_gbp=Decimal("600"),
        )
        assert ret.shortfall_gbp == Decimal("600")

    def test_to_dict_types(self):
        ret = self._gen().build(
            total_client_funds_gbp=Decimal("50000"),
            safeguarding_balance_gbp=Decimal("50000"),
            num_safeguarding_accounts=2,
            safeguarding_bank="HSBC",
            daily_recon_count=21,
            daily_recon_breaks=1,
        )
        d = ret.to_dict()
        assert isinstance(d["total_client_funds_gbp"], str)
        assert isinstance(d["reference_month"], str)
        assert d["institution_name"] == "Banxe Ltd"

    def test_to_csv_row_contains_frn(self):
        ret = self._gen().build(
            total_client_funds_gbp=Decimal("50000"),
            safeguarding_balance_gbp=Decimal("50000"),
            num_safeguarding_accounts=1,
            safeguarding_bank="Barclays",
            daily_recon_count=22,
            daily_recon_breaks=0,
        )
        row = ret.to_csv_row()
        assert "987654" in row

    def test_month_label(self):
        ret = self._gen().build(
            total_client_funds_gbp=Decimal("1"),
            safeguarding_balance_gbp=Decimal("1"),
            num_safeguarding_accounts=1,
            safeguarding_bank="Barclays",
            daily_recon_count=1,
            daily_recon_breaks=0,
        )
        assert ret.month_label == "April 2026"

    def test_to_json_is_valid(self):
        import json

        ret = self._gen().build(
            total_client_funds_gbp=Decimal("1000"),
            safeguarding_balance_gbp=Decimal("1000"),
            num_safeguarding_accounts=1,
            safeguarding_bank="Barclays",
            daily_recon_count=22,
            daily_recon_breaks=0,
        )
        parsed = json.loads(ret.to_json())
        assert parsed["frn"] == "987654"


# ---------------------------------------------------------------------------
# AuditTrail
# ---------------------------------------------------------------------------


class TestAuditTrail:
    def _trail(self, dry_run=True):
        from src.safeguarding.audit_trail import AuditTrail

        return AuditTrail(dry_run=dry_run)

    def _event(self, event_type="RECON_BREAK"):
        from src.safeguarding.audit_trail import AuditEvent

        return AuditEvent(
            event_type=event_type,
            entity_id="recon-2026-04-13",
            actor="DailyReconciliation",
            payload={"diff_gbp": "50.00"},
            severity="CRITICAL",
        )

    def test_dry_run_returns_true(self):
        trail = self._trail(dry_run=True)
        assert trail.log(self._event()) is True

    def test_event_has_uuid(self):
        import uuid

        event = self._event()
        uuid.UUID(event.event_id)  # raises if invalid

    def test_payload_json(self):
        import json

        event = self._event()
        parsed = json.loads(event.payload_json())
        assert parsed["diff_gbp"] == "50.00"

    def test_log_does_not_raise_on_exception(self):
        from src.safeguarding.audit_trail import AuditTrail

        trail = AuditTrail(dry_run=False, clickhouse_url="http://0.0.0.0:1")
        # Should not raise — fail-open
        result = trail.log(self._event())
        assert result is False  # graceful failure

    def test_ensure_table_dry_run_noop(self):
        trail = self._trail(dry_run=True)
        trail.ensure_table()  # must not raise or call httpx

    def test_audit_event_default_severity(self):
        from src.safeguarding.audit_trail import AuditEvent

        ev = AuditEvent(
            event_type="FIN060_SUBMITTED", entity_id="fin060-apr-2026", actor="FIN060Generator"
        )
        assert ev.severity == "INFO"
