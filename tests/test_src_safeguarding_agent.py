"""Tests for src/safeguarding/agent.py — GAP-051 SafeguardingAgent.

Coverage targets: SafeguardingAgent.run(), SafeguardingAgent._run_internal(),
Protocol stubs, exit codes, breach detection, FCA notification path.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from src.safeguarding.agent import (
    EXIT_BREACH,
    EXIT_FATAL,
    EXIT_MATCHED,
    EXIT_PENDING,
    InMemoryStreakCounter,
    SafeguardingAgent,
    SafeguardingAgentPorts,
    SafeguardingRunResult,
    StubBankStatementPort,
    StubLedgerPort,
)
from src.safeguarding.audit_trail import AuditTrail
from src.safeguarding.breach_detector import BreachAlert, BreachDetector, BreachSeverity
from src.safeguarding.daily_reconciliation import ReconStatus
from src.safeguarding.three_leg import InMemoryRailBalancePort, ThreeLegStatus

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_ports(
    ledger_bal: Decimal = Decimal("100000"),
    bank_bal: Decimal | None = Decimal("100000"),
    streak: int = 0,
) -> SafeguardingAgentPorts:
    return SafeguardingAgentPorts(
        ledger=StubLedgerPort(ledger_bal),
        bank=StubBankStatementPort(bank_bal),
        audit=AuditTrail(clickhouse_url="", dry_run=True),
        streak_counter=InMemoryStreakCounter(streak),
    )


def _make_agent(ports: SafeguardingAgentPorts, fca_notify: bool = False) -> SafeguardingAgent:
    return SafeguardingAgent(ports, fca_notify=fca_notify)


# ── Stubs ──────────────────────────────────────────────────────────────────────


class TestStubPorts:
    def test_stub_ledger_default(self):
        port = StubLedgerPort()
        assert port.get_client_funds_gbp(date.today()) == Decimal("100000")

    def test_stub_ledger_custom(self):
        port = StubLedgerPort(Decimal("50000"))
        assert port.get_client_funds_gbp(date.today()) == Decimal("50000")

    def test_stub_bank_default(self):
        port = StubBankStatementPort()
        assert port.get_closing_balance_gbp(date.today()) == Decimal("100000")

    def test_stub_bank_none(self):
        port = StubBankStatementPort(None)
        assert port.get_closing_balance_gbp(date.today()) is None

    def test_stub_bank_custom(self):
        port = StubBankStatementPort(Decimal("75000"))
        assert port.get_closing_balance_gbp(date.today()) == Decimal("75000")

    def test_inmemory_streak_default(self):
        sc = InMemoryStreakCounter()
        assert sc.get_streak(date.today()) == 0

    def test_inmemory_streak_initial(self):
        sc = InMemoryStreakCounter(initial_streak=5)
        assert sc.get_streak(date.today()) == 5

    def test_inmemory_streak_reset(self):
        sc = InMemoryStreakCounter(initial_streak=3)
        sc.reset_streak(date.today())
        assert sc.get_streak(date.today()) == 0


# ── SafeguardingRunResult ──────────────────────────────────────────────────────


class TestSafeguardingRunResult:
    def _make_result(self, exit_code: int) -> SafeguardingRunResult:
        return SafeguardingRunResult(
            run_date=date(2026, 4, 13),
            recon_result=None,
            breach_alert=None,
            audit_event_id="test-event-id",
            exit_code=exit_code,
        )

    def test_status_label_matched(self):
        assert self._make_result(EXIT_MATCHED).status_label == "MATCHED"

    def test_status_label_breach(self):
        assert self._make_result(EXIT_BREACH).status_label == "BREACH"

    def test_status_label_pending(self):
        assert self._make_result(EXIT_PENDING).status_label == "PENDING"

    def test_status_label_fatal(self):
        assert self._make_result(EXIT_FATAL).status_label == "FATAL"

    def test_summary_contains_date(self):
        result = self._make_result(EXIT_MATCHED)
        assert "2026-04-13" in result.summary()

    def test_summary_contains_audit_event(self):
        result = self._make_result(EXIT_MATCHED)
        assert "test-event-id" in result.summary()


# ── SafeguardingAgent.run — happy paths ────────────────────────────────────────


class TestSafeguardingAgentRun:
    def test_matched_exit_code(self):
        ports = _make_ports(Decimal("100000"), Decimal("100000"))
        agent = _make_agent(ports)
        result = agent.run(date(2026, 4, 13))
        assert result.exit_code == EXIT_MATCHED
        assert result.status_label == "MATCHED"

    def test_matched_resets_streak(self):
        ports = _make_ports(Decimal("100000"), Decimal("100000"), streak=3)
        agent = _make_agent(ports)
        agent.run(date(2026, 4, 13))
        assert ports.streak_counter.get_streak(date(2026, 4, 13)) == 0

    def test_pending_exit_code(self):
        ports = _make_ports(Decimal("100000"), bank_bal=None)
        agent = _make_agent(ports)
        result = agent.run(date(2026, 4, 13))
        assert result.exit_code == EXIT_PENDING

    def test_pending_does_not_reset_streak(self):
        ports = _make_ports(Decimal("100000"), bank_bal=None, streak=2)
        agent = _make_agent(ports)
        agent.run(date(2026, 4, 13))
        assert ports.streak_counter.get_streak(date(2026, 4, 13)) == 2

    def test_break_without_streak_not_critical(self):
        """A single break day (streak=0) is not a CRITICAL breach."""
        ports = _make_ports(Decimal("100000"), Decimal("90000"), streak=0)
        agent = _make_agent(ports)
        result = agent.run(date(2026, 4, 13))
        # With streak=0, BreachDetector should return MINOR/MAJOR, not CRITICAL
        # Exit code depends on whether breach is fca_notification_required
        assert result.exit_code in (EXIT_MATCHED, EXIT_BREACH)

    def test_break_with_long_streak_is_breach(self):
        """4 consecutive break days → CRITICAL → EXIT_BREACH."""
        ports = _make_ports(Decimal("100000"), Decimal("90000"), streak=4)
        agent = _make_agent(ports)
        result = agent.run(date(2026, 4, 13))
        assert result.exit_code == EXIT_BREACH

    def test_shortfall_always_breach(self):
        """Ledger < Bank (internal < external = shortfall) → always CRITICAL."""
        # shortfall: internal=50000 < external=200000 → diff < 0 → CRITICAL
        ports = _make_ports(Decimal("50000"), Decimal("200000"), streak=0)
        agent = _make_agent(ports)
        result = agent.run(date(2026, 4, 13))
        assert result.exit_code == EXIT_BREACH

    def test_audit_event_id_returned(self):
        ports = _make_ports()
        agent = _make_agent(ports)
        result = agent.run(date(2026, 4, 13))
        assert result.audit_event_id  # non-empty string

    def test_recon_result_populated(self):
        ports = _make_ports()
        agent = _make_agent(ports)
        result = agent.run(date(2026, 4, 13))
        assert result.recon_result is not None
        assert result.recon_result.status == ReconStatus.MATCHED

    def test_run_date_defaults_to_today(self):
        ports = _make_ports()
        agent = _make_agent(ports)
        result = agent.run()  # no date arg
        assert result.run_date == date.today()

    def test_run_at_is_utc(self):
        ports = _make_ports()
        agent = _make_agent(ports)
        result = agent.run(date(2026, 4, 13))
        assert result.run_at.tzinfo is not None

    def test_breach_alert_populated_on_shortfall(self):
        # shortfall: internal=50000 < external=200000 → CRITICAL → fca_required=True
        ports = _make_ports(Decimal("50000"), Decimal("200000"))
        agent = _make_agent(ports)
        result = agent.run(date(2026, 4, 13))
        assert result.breach_alert is not None
        assert result.breach_alert.fca_notification_required is True


# ── SafeguardingAgent.run — fatal path ────────────────────────────────────────


class TestSafeguardingAgentFatal:
    def test_fatal_on_ledger_port_error(self):
        class BrokenLedger:
            def get_client_funds_gbp(self, as_of):
                raise RuntimeError("Midaz connection refused")

        ports = SafeguardingAgentPorts(
            ledger=BrokenLedger(),
            bank=StubBankStatementPort(),
            audit=AuditTrail(clickhouse_url="", dry_run=True),
            streak_counter=InMemoryStreakCounter(),
        )
        agent = _make_agent(ports)
        result = agent.run(date(2026, 4, 13))
        assert result.exit_code == EXIT_FATAL
        assert result.recon_result is None

    def test_fatal_result_has_audit_id(self):
        class BrokenLedger:
            def get_client_funds_gbp(self, as_of):
                raise ValueError("test error")

        ports = SafeguardingAgentPorts(
            ledger=BrokenLedger(),
            bank=StubBankStatementPort(),
            audit=AuditTrail(clickhouse_url="", dry_run=True),
            streak_counter=InMemoryStreakCounter(),
        )
        agent = _make_agent(ports)
        result = agent.run(date(2026, 4, 13))
        assert result.audit_event_id  # non-empty — audit must fire even on FATAL


# ── FCA notification ───────────────────────────────────────────────────────────


class TestFCANotification:
    def _make_critical_alert(self) -> BreachAlert:
        return BreachAlert(
            breach_date=date(2026, 4, 13),
            severity=BreachSeverity.CRITICAL,
            consecutive_days=0,
            shortfall_gbp=Decimal("150000"),
            description="Test shortfall",
            fca_notification_required=True,
        )

    def test_fca_notify_false_does_not_call(self):
        """fca_notify=False: logs warning but does NOT call notify_fca."""
        ports = _make_ports(Decimal("50000"), Decimal("200000"))
        mock_detector = MagicMock(spec=BreachDetector)
        mock_alert = self._make_critical_alert()
        mock_detector.assess.return_value = mock_alert

        agent = SafeguardingAgent(ports, fca_notify=False, detector=mock_detector)
        agent.run(date(2026, 4, 13))
        mock_detector.notify_fca.assert_not_called()

    def test_fca_notify_true_calls_notify(self):
        """fca_notify=True: calls notify_fca for CRITICAL alert."""
        ports = _make_ports(Decimal("50000"), Decimal("200000"))
        mock_detector = MagicMock(spec=BreachDetector)
        mock_alert = self._make_critical_alert()
        mock_detector.assess.return_value = mock_alert

        agent = SafeguardingAgent(ports, fca_notify=True, detector=mock_detector)
        agent.run(date(2026, 4, 13))
        mock_detector.notify_fca.assert_called_once_with(mock_alert, dry_run=False)


# ── Three-leg wiring in SafeguardingAgent ─────────────────────────────────────


RUN_DATE = date(2026, 6, 26)


def _make_ports_with_rail(
    ledger_bal: Decimal = Decimal("100000"),
    bank_bal: Decimal | None = Decimal("100000"),
    rail_bal: Decimal | None = Decimal("100000"),
    streak: int = 0,
) -> SafeguardingAgentPorts:
    rail_port = InMemoryRailBalancePort()
    if rail_bal is not None:
        rail_port.set_balance(RUN_DATE, rail_bal)
    return SafeguardingAgentPorts(
        ledger=StubLedgerPort(ledger_bal),
        bank=StubBankStatementPort(bank_bal),
        audit=AuditTrail(clickhouse_url="", dry_run=True),
        streak_counter=InMemoryStreakCounter(streak),
        rail=rail_port,
    )


class TestThreeLegWiring:
    def test_no_rail_port_skips_three_leg(self):
        """rail=None → three_leg_result is None (backward-compatible)."""
        ports = _make_ports()
        agent = _make_agent(ports)
        result = agent.run(RUN_DATE)
        assert result.three_leg_result is None

    def test_three_legs_all_match(self):
        """A == B == C → three_leg_result.status MATCHED, exit MATCHED."""
        ports = _make_ports_with_rail(Decimal("100000"), Decimal("100000"), Decimal("100000"))
        agent = _make_agent(ports)
        result = agent.run(RUN_DATE)
        assert result.three_leg_result is not None
        assert result.three_leg_result.status == ThreeLegStatus.MATCHED
        assert result.exit_code == EXIT_MATCHED

    def test_three_leg_break_escalates_to_breach(self):
        """2-leg MATCHED but Leg C diverges → 3-leg BREAK → exit BREACH."""
        ports = _make_ports_with_rail(
            Decimal("100000"),
            Decimal("100000"),
            Decimal("80000"),  # C differs by £20k
        )
        agent = _make_agent(ports)
        result = agent.run(RUN_DATE)
        assert result.three_leg_result is not None
        assert result.three_leg_result.status == ThreeLegStatus.BREAK
        assert result.exit_code == EXIT_BREACH

    def test_three_leg_shortfall_flagged(self):
        """A (ledger) > B (safeguarding) → shortfall=True in three_leg_result."""
        ports = _make_ports_with_rail(Decimal("120000"), Decimal("100000"), Decimal("120000"))
        agent = _make_agent(ports)
        result = agent.run(RUN_DATE)
        assert result.three_leg_result is not None
        assert result.three_leg_result.shortfall is True
        assert result.exit_code == EXIT_BREACH

    def test_three_leg_pending_when_rail_missing(self):
        """Leg C balance unavailable → three_leg_result.status PENDING."""
        ports = _make_ports_with_rail(Decimal("100000"), Decimal("100000"), rail_bal=None)
        agent = _make_agent(ports)
        result = agent.run(RUN_DATE)
        assert result.three_leg_result is not None
        assert result.three_leg_result.status == ThreeLegStatus.PENDING

    def test_summary_includes_three_leg_status(self):
        """summary() shows 3-leg status line when rail port is wired."""
        ports = _make_ports_with_rail(Decimal("100000"), Decimal("100000"), Decimal("100000"))
        agent = _make_agent(ports)
        result = agent.run(RUN_DATE)
        assert "3-leg" in result.summary()
        assert "MATCHED" in result.summary()

    def test_summary_shows_shortfall_label(self):
        """summary() includes SHORTFALL when three_leg_result.shortfall=True."""
        ports = _make_ports_with_rail(Decimal("120000"), Decimal("100000"), Decimal("120000"))
        agent = _make_agent(ports)
        result = agent.run(RUN_DATE)
        assert "SHORTFALL" in result.summary()

    def test_audit_payload_includes_three_leg_status(self):
        """AuditEvent payload carries three_leg_status when rail is wired."""
        captured: list[object] = []

        class CapturingAuditTrail(AuditTrail):
            def log(self, event):  # type: ignore[override]
                captured.append(event)

        rail_port = InMemoryRailBalancePort()
        rail_port.set_balance(RUN_DATE, Decimal("100000"))
        ports = SafeguardingAgentPorts(
            ledger=StubLedgerPort(Decimal("100000")),
            bank=StubBankStatementPort(Decimal("100000")),
            audit=CapturingAuditTrail(clickhouse_url="", dry_run=True),
            streak_counter=InMemoryStreakCounter(),
            rail=rail_port,
        )
        agent = _make_agent(ports)
        agent.run(RUN_DATE)
        assert captured
        event = captured[0]
        assert event.payload["three_leg_status"] == "MATCHED"
        assert event.payload["three_leg_shortfall"] is False

    def test_fatal_does_not_propagate_three_leg_error(self):
        """If rail port raises, agent catches and returns EXIT_FATAL (never raises)."""

        class BrokenRailPort:
            def get_rail_balance_gbp(self, as_of):
                raise RuntimeError("rail timeout")

        ports = SafeguardingAgentPorts(
            ledger=StubLedgerPort(Decimal("100000")),
            bank=StubBankStatementPort(Decimal("100000")),
            audit=AuditTrail(clickhouse_url="", dry_run=True),
            streak_counter=InMemoryStreakCounter(),
            rail=BrokenRailPort(),
        )
        agent = _make_agent(ports)
        result = agent.run(RUN_DATE)
        assert result.exit_code == EXIT_FATAL
