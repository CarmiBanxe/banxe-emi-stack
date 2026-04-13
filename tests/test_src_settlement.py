"""Tests for src/settlement/reconciler_engine.py — GAP-010 D-recon.

Covers:
  TriPartyReconciler  — all three legs: MATCHED / DISCREPANCY / PENDING
  ReconcilerCron      — exit codes 0/1/2/3
  ClickHouseDiscrepancyReporter — insert SQL, fallback on httpx failure
  NullDiscrepancyReporter       — no-op, no raises
  TriPartyResult.summary/to_dict — serialisation
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

# ── helpers ───────────────────────────────────────────────────────────────────

DATE = date(2026, 4, 13)


def _ledger(client_funds="100000", operational="0", source="midaz"):
    from src.settlement.reconciler_engine import LedgerBalance

    return LedgerBalance(
        settlement_date=DATE,
        total_client_funds_gbp=Decimal(client_funds),
        total_operational_gbp=Decimal(operational),
        source=source,
    )


def _bank(closing="100000", source_file="camt053_20260413.xml"):
    from src.settlement.reconciler_engine import SafeguardingBalance

    return SafeguardingBalance(
        statement_date=DATE,
        closing_balance_gbp=Decimal(closing),
        available_balance_gbp=Decimal(closing),
        source_file=source_file,
    )


def _rails(net="100000", count=150):
    from src.settlement.reconciler_engine import RailsBalance

    return RailsBalance(
        settlement_date=DATE,
        total_settled_gbp=Decimal(net),
        source="hyperswitch",
        transaction_count=count,
    )


def _make_ports(ledger_data=None, bank_data=None, rails_data=None):
    """Build stub port classes returning supplied data."""

    ld = ledger_data or _ledger()
    bd = bank_data  # None = PENDING
    rd = rails_data or _rails()

    class StubLedger:
        def get_gl_balance(self, d):
            return ld

    class StubBank:
        def get_closing_balance(self, d):
            return bd

    class StubRails:
        def get_settled_total(self, d):
            return rd

    return StubLedger(), StubBank(), StubRails()


def _make_reporter():
    from src.settlement.reconciler_engine import NullDiscrepancyReporter

    reporter = NullDiscrepancyReporter()
    reporter._calls = []
    _orig = reporter.report

    def _capturing_report(result):
        reporter._calls.append(result)
        _orig(result)

    reporter.report = _capturing_report
    return reporter


def _make_reconciler(ledger_data=None, bank_data=None, rails_data=None, tolerance="1.00"):
    from src.settlement.reconciler_engine import TriPartyReconciler

    ledger_p, bank_p, rails_p = _make_ports(ledger_data, bank_data, rails_data)
    reporter = _make_reporter()
    engine = TriPartyReconciler(
        ledger_port=ledger_p,
        bank_port=bank_p,
        rails_port=rails_p,
        reporter=reporter,
        tolerance=Decimal(tolerance),
    )
    return engine, reporter


# ── LedgerBalance ─────────────────────────────────────────────────────────────


class TestLedgerBalance:
    def test_net_position(self):
        lb = _ledger(client_funds="100000", operational="5000")
        assert lb.net_position_gbp == Decimal("105000")

    def test_net_position_zero_operational(self):
        lb = _ledger(client_funds="50000", operational="0")
        assert lb.net_position_gbp == Decimal("50000")


# ── RailsBalance ──────────────────────────────────────────────────────────────


class TestRailsBalance:
    def test_net_settled_no_refunds(self):
        from src.settlement.reconciler_engine import RailsBalance

        rb = RailsBalance(DATE, Decimal("10000"), transaction_count=5)
        assert rb.net_settled_gbp == Decimal("10000")

    def test_net_settled_with_refunds(self):
        from src.settlement.reconciler_engine import RailsBalance

        rb = RailsBalance(DATE, Decimal("10000"), total_refunded_gbp=Decimal("500"))
        assert rb.net_settled_gbp == Decimal("9500")


# ── TriPartyReconciler — MATCHED ──────────────────────────────────────────────


class TestTriPartyReconcilerMatched:
    def test_all_equal_all_matched(self):
        from src.settlement.reconciler_engine import TriPartyStatus

        engine, reporter = _make_reconciler(
            ledger_data=_ledger("100000"),
            bank_data=_bank("100000"),
            rails_data=_rails("100000"),
        )
        result = engine.reconcile(DATE)
        assert result.overall_status == TriPartyStatus.MATCHED
        assert all(leg.status == "MATCHED" for leg in result.legs)
        assert len(reporter._calls) == 1

    def test_within_tolerance_matched(self):
        from src.settlement.reconciler_engine import TriPartyStatus

        engine, reporter = _make_reconciler(
            ledger_data=_ledger("100000"),
            bank_data=_bank("100000.50"),
            rails_data=_rails("100000"),
            tolerance="1.00",
        )
        result = engine.reconcile(DATE)
        assert result.overall_status == TriPartyStatus.MATCHED

    def test_three_legs_present(self):
        engine, _ = _make_reconciler(
            ledger_data=_ledger("100000"),
            bank_data=_bank("100000"),
            rails_data=_rails("100000"),
        )
        result = engine.reconcile(DATE)
        from src.settlement.reconciler_engine import ReconLeg

        leg_names = {lr.leg for lr in result.legs}
        assert ReconLeg.RAILS_VS_LEDGER in leg_names
        assert ReconLeg.LEDGER_VS_BANK in leg_names
        assert ReconLeg.RAILS_VS_BANK in leg_names


# ── TriPartyReconciler — DISCREPANCY ──────────────────────────────────────────


class TestTriPartyReconcilerDiscrepancy:
    def test_rails_vs_ledger_discrepancy(self):
        from src.settlement.reconciler_engine import TriPartyStatus

        engine, _ = _make_reconciler(
            ledger_data=_ledger("100000"),
            bank_data=_bank("100000"),
            rails_data=_rails("98000"),  # £2k shortfall on rails
            tolerance="1.00",
        )
        result = engine.reconcile(DATE)
        assert result.overall_status == TriPartyStatus.DISCREPANCY

    def test_ledger_vs_bank_discrepancy(self):
        from src.settlement.reconciler_engine import TriPartyStatus

        engine, _ = _make_reconciler(
            ledger_data=_ledger("100000"),
            bank_data=_bank("97500"),  # £2.5k shortfall in bank
            rails_data=_rails("100000"),
            tolerance="1.00",
        )
        result = engine.reconcile(DATE)
        assert result.overall_status == TriPartyStatus.DISCREPANCY

    def test_discrepancy_leg_has_note(self):
        engine, _ = _make_reconciler(
            ledger_data=_ledger("100000"),
            bank_data=_bank("99000"),
            rails_data=_rails("100000"),
        )
        result = engine.reconcile(DATE)
        discrepancy_legs = [lr for lr in result.legs if lr.status == "DISCREPANCY"]
        assert any(len(lr.note) > 0 for lr in discrepancy_legs)

    def test_discrepancy_difference_correct(self):
        from src.settlement.reconciler_engine import ReconLeg

        engine, _ = _make_reconciler(
            ledger_data=_ledger("100000"),
            bank_data=_bank("99000"),
            rails_data=_rails("100000"),
        )
        result = engine.reconcile(DATE)
        leg2 = next(lr for lr in result.legs if lr.leg == ReconLeg.LEDGER_VS_BANK)
        assert leg2.difference_gbp == Decimal("1000")
        assert leg2.abs_difference == Decimal("1000")


# ── TriPartyReconciler — PENDING ──────────────────────────────────────────────


class TestTriPartyReconcilerPending:
    def test_no_bank_statement_all_bank_legs_pending(self):
        from src.settlement.reconciler_engine import ReconLeg, TriPartyStatus

        engine, _ = _make_reconciler(
            ledger_data=_ledger("100000"),
            bank_data=None,
            rails_data=_rails("100000"),
        )
        result = engine.reconcile(DATE)
        assert result.overall_status == TriPartyStatus.PENDING
        assert result.safeguarding is None
        bank_legs = [lr for lr in result.legs if lr.leg != ReconLeg.RAILS_VS_LEDGER]
        assert all(lr.status == "PENDING" for lr in bank_legs)

    def test_leg1_can_match_even_when_bank_pending(self):
        from src.settlement.reconciler_engine import ReconLeg, TriPartyStatus

        engine, _ = _make_reconciler(
            ledger_data=_ledger("100000"),
            bank_data=None,
            rails_data=_rails("100000"),
        )
        result = engine.reconcile(DATE)
        leg1 = next(lr for lr in result.legs if lr.leg == ReconLeg.RAILS_VS_LEDGER)
        assert leg1.status == "MATCHED"
        assert result.overall_status == TriPartyStatus.PENDING  # pending beats matched


# ── TriPartyResult serialisation ─────────────────────────────────────────────


class TestTriPartyResultSerialisation:
    def test_to_dict_types(self):
        engine, _ = _make_reconciler(
            ledger_data=_ledger("100000"),
            bank_data=_bank("100000"),
            rails_data=_rails("100000"),
        )
        result = engine.reconcile(DATE)
        d = result.to_dict()
        assert d["overall_status"] == "MATCHED"
        assert isinstance(d["rails_net_gbp"], str)
        assert isinstance(d["midaz_client_funds_gbp"], str)
        assert isinstance(d["legs"], list)
        assert len(d["legs"]) == 3

    def test_to_dict_pending_bank_is_none(self):
        engine, _ = _make_reconciler(bank_data=None)
        result = engine.reconcile(DATE)
        d = result.to_dict()
        assert d["safeguarding_closing_gbp"] is None

    def test_summary_contains_status(self):
        engine, _ = _make_reconciler(
            ledger_data=_ledger("100000"),
            bank_data=_bank("100000"),
            rails_data=_rails("100000"),
        )
        result = engine.reconcile(DATE)
        summary = result.summary()
        assert "MATCHED" in summary
        assert "£" in summary


# ── ReconcilerCron exit codes ─────────────────────────────────────────────────


class TestReconcilerCron:
    def _cron(self, ledger_data=None, bank_data=None, rails_data=None, tolerance="1.00"):
        from src.settlement.reconciler_engine import NullDiscrepancyReporter, ReconcilerCron

        ledger_p, bank_p, rails_p = _make_ports(ledger_data, bank_data, rails_data)
        return ReconcilerCron(
            ledger_port=ledger_p,
            bank_port=bank_p,
            rails_port=rails_p,
            reporter=NullDiscrepancyReporter(),
            tolerance=Decimal(tolerance),
        )

    def test_exit_0_on_matched(self):
        cron = self._cron(
            ledger_data=_ledger("100000"),
            bank_data=_bank("100000"),
            rails_data=_rails("100000"),
        )
        assert cron.run(DATE) == 0

    def test_exit_1_on_discrepancy(self):
        cron = self._cron(
            ledger_data=_ledger("100000"),
            bank_data=_bank("95000"),
            rails_data=_rails("100000"),
        )
        assert cron.run(DATE) == 1

    def test_exit_2_on_pending(self):
        cron = self._cron(bank_data=None)
        assert cron.run(DATE) == 2

    def test_exit_3_on_fatal(self):
        from src.settlement.reconciler_engine import NullDiscrepancyReporter, ReconcilerCron

        class _BrokenLedger:
            def get_gl_balance(self, d):
                raise RuntimeError("Midaz unreachable")

        class _StubBank:
            def get_closing_balance(self, d):
                return None

        class _StubRails:
            def get_settled_total(self, d):
                return _rails()

        cron = ReconcilerCron(
            ledger_port=_BrokenLedger(),
            bank_port=_StubBank(),
            rails_port=_StubRails(),
            reporter=NullDiscrepancyReporter(),
        )
        assert cron.run(DATE) == 3

    def test_output_json_flag_does_not_raise(self, capsys):
        cron = self._cron(
            ledger_data=_ledger("100000"),
            bank_data=_bank("100000"),
            rails_data=_rails("100000"),
        )
        exit_code = cron.run(DATE, output_json=True)
        captured = capsys.readouterr()
        import json

        parsed = json.loads(captured.out)
        assert parsed["overall_status"] == "MATCHED"
        assert exit_code == 0


# ── NullDiscrepancyReporter ───────────────────────────────────────────────────


class TestNullDiscrepancyReporter:
    def test_does_not_raise_on_matched(self):
        from src.settlement.reconciler_engine import NullDiscrepancyReporter

        engine, _ = _make_reconciler()
        result = engine.reconcile(DATE)
        NullDiscrepancyReporter().report(result)  # must not raise

    def test_does_not_raise_on_discrepancy(self):
        from src.settlement.reconciler_engine import NullDiscrepancyReporter

        engine, _ = _make_reconciler(bank_data=_bank("50000"))
        result = engine.reconcile(DATE)
        NullDiscrepancyReporter().report(result)  # must not raise


# ── ClickHouseDiscrepancyReporter ─────────────────────────────────────────────


class TestClickHouseDiscrepancyReporter:
    def test_report_calls_httpx_post(self):
        from src.settlement.reconciler_engine import ClickHouseDiscrepancyReporter

        engine, _ = _make_reconciler(
            ledger_data=_ledger("100000"),
            bank_data=_bank("100000"),
            rails_data=_rails("100000"),
        )
        result = engine.reconcile(DATE)

        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None

        with patch("httpx.post", return_value=mock_resp) as mock_post:
            reporter = ClickHouseDiscrepancyReporter()
            reporter.report(result)
            mock_post.assert_called_once()
            _, kwargs = mock_post.call_args
            sql = kwargs.get("params", {}).get("query", "")
            assert "settlement_recon_events" in sql

    def test_report_fallback_on_httpx_error(self):
        from src.settlement.reconciler_engine import ClickHouseDiscrepancyReporter

        engine, _ = _make_reconciler()
        result = engine.reconcile(DATE)

        with patch("httpx.post", side_effect=Exception("CH unavailable")):
            reporter = ClickHouseDiscrepancyReporter()
            reporter.report(result)  # must not raise

    def test_report_without_bank_uses_null(self):
        from src.settlement.reconciler_engine import ClickHouseDiscrepancyReporter

        engine, _ = _make_reconciler(bank_data=None)
        result = engine.reconcile(DATE)

        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None

        with patch("httpx.post", return_value=mock_resp) as mock_post:
            reporter = ClickHouseDiscrepancyReporter()
            reporter.report(result)
            mock_post.assert_called_once()
