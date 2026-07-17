"""Tests for services/recon/safeguarding_adapters.py and
_run_safeguarding_agent() in cron_daily_recon.py.

All tests are offline (no Midaz, no ClickHouse). Adapters are unit-tested by
stubbing the underlying MidazLedgerAdapter / StatementFetcher via monkeypatch
or direct stub injection.

Coverage targets:
  - MidazClientFundsPort.get_client_funds_gbp()
  - StatementBankPort.get_closing_balance_gbp() — summing, PENDING on empty
  - ZeroStreakCounter.get_streak() / reset_streak()
  - _run_safeguarding_agent() — matched, fatal paths, exit code mapping
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from services.recon.safeguarding_adapters import (
    MidazClientFundsPort,
    StatementBankPort,
    ZeroStreakCounter,
)

D = date(2026, 6, 26)


# ── ZeroStreakCounter ─────────────────────────────────────────────────────────


class TestZeroStreakCounter:
    def test_get_streak_always_zero(self):
        assert ZeroStreakCounter().get_streak(D) == 0

    def test_reset_streak_is_noop(self):
        sc = ZeroStreakCounter()
        sc.reset_streak(D)  # should not raise
        assert sc.get_streak(D) == 0


# ── MidazClientFundsPort ──────────────────────────────────────────────────────


class TestMidazClientFundsPort:
    def _make_port(self, balance: Decimal) -> MidazClientFundsPort:
        mock_adapter = MagicMock()
        mock_adapter.get_balance.return_value = balance
        port = MidazClientFundsPort.__new__(MidazClientFundsPort)
        port._org_id = "org-1"
        port._ledger_id = "led-1"
        port._account_id = "acct-1"
        port._midaz = mock_adapter
        return port

    def test_returns_midaz_balance(self):
        port = self._make_port(Decimal("100000.00"))
        assert port.get_client_funds_gbp(D) == Decimal("100000.00")

    def test_returns_decimal_not_float(self):
        port = self._make_port(Decimal("99999.99"))
        result = port.get_client_funds_gbp(D)
        assert isinstance(result, Decimal)

    def test_calls_get_balance_with_org_ledger_account(self):
        port = self._make_port(Decimal("50000.00"))
        port.get_client_funds_gbp(D)
        port._midaz.get_balance.assert_called_once_with("org-1", "led-1", "acct-1")

    def test_env_override_org_id(self, monkeypatch):
        monkeypatch.setenv("MIDAZ_ORG_ID", "custom-org")
        # Lazy import in __init__ — patch at the source module, not the adapter
        with patch("services.ledger.midaz_adapter.MidazLedgerAdapter") as mock_cls:
            mock_cls.return_value.get_balance.return_value = Decimal("1.00")
            port = MidazClientFundsPort()
            assert port._org_id == "custom-org"


# ── StatementBankPort ─────────────────────────────────────────────────────────


class TestStatementBankPort:
    def _make_port(self, balances: list) -> StatementBankPort:
        from services.recon.statement_fetcher import StatementBalance

        mock_fetcher = MagicMock()
        mock_fetcher.fetch.return_value = [
            StatementBalance(
                account_id=f"acct-{i}",
                currency=b["currency"],
                balance=b["balance"],
                statement_date=D,
                source_file="test.csv",
            )
            for i, b in enumerate(balances)
        ]
        port = StatementBankPort.__new__(StatementBankPort)
        port._fetcher = mock_fetcher
        return port

    def test_single_gbp_account_returns_balance(self):
        port = self._make_port([{"currency": "GBP", "balance": Decimal("50000.00")}])
        assert port.get_closing_balance_gbp(D) == Decimal("50000.00")

    def test_multiple_gbp_accounts_summed(self):
        port = self._make_port(
            [
                {"currency": "GBP", "balance": Decimal("30000.00")},
                {"currency": "GBP", "balance": Decimal("20000.00")},
            ]
        )
        assert port.get_closing_balance_gbp(D) == Decimal("50000.00")

    def test_non_gbp_accounts_excluded(self):
        port = self._make_port(
            [
                {"currency": "GBP", "balance": Decimal("50000.00")},
                {"currency": "EUR", "balance": Decimal("10000.00")},
            ]
        )
        assert port.get_closing_balance_gbp(D) == Decimal("50000.00")

    def test_no_gbp_accounts_returns_pending(self):
        port = self._make_port([{"currency": "EUR", "balance": Decimal("10000.00")}])
        assert port.get_closing_balance_gbp(D) is None

    def test_empty_statement_returns_pending(self):
        port = self._make_port([])
        assert port.get_closing_balance_gbp(D) is None

    def test_result_is_decimal(self):
        port = self._make_port([{"currency": "GBP", "balance": Decimal("12345.67")}])
        result = port.get_closing_balance_gbp(D)
        assert isinstance(result, Decimal)


# ── _run_safeguarding_agent ───────────────────────────────────────────────────


class TestRunSafeguardingAgent:
    # _run_safeguarding_agent uses lazy imports (PLC0415), so we patch at
    # source modules, not at the cron_daily_recon namespace.
    _SA_AGENT = "src.safeguarding.agent.SafeguardingAgent"
    _SA_PORTS = "src.safeguarding.agent.SafeguardingAgentPorts"
    _SA_AUDIT = "src.safeguarding.audit_trail.AuditTrail"
    _SA_RAIL = "src.safeguarding.three_leg.InMemoryRailBalancePort"
    _MIDAZ_PORT = "services.recon.safeguarding_adapters.MidazClientFundsPort"
    _STMT_PORT = "services.recon.safeguarding_adapters.StatementBankPort"
    _STREAK = "services.recon.safeguarding_adapters.ZeroStreakCounter"

    def test_matched_returns_exit_matched(self):
        from services.recon.cron_daily_recon import EXIT_MATCHED, _run_safeguarding_agent

        with (
            patch(self._MIDAZ_PORT),
            patch(self._STMT_PORT),
            patch(self._STREAK),
            patch(self._SA_AUDIT),
            patch(self._SA_RAIL),
            patch(self._SA_PORTS),
            patch(self._SA_AGENT) as mock_agent_cls,
        ):
            mock_result = MagicMock()
            mock_result.exit_code = 0
            mock_result.status_label = "MATCHED"
            mock_result.three_leg_result = None
            mock_agent_cls.return_value.run.return_value = mock_result
            exit_code = _run_safeguarding_agent(D, dry_run=True)
        assert exit_code == EXIT_MATCHED

    def test_breach_maps_to_discrepancy(self):
        from services.recon.cron_daily_recon import (
            EXIT_DISCREPANCY,
            _run_safeguarding_agent,
        )

        with (
            patch(self._MIDAZ_PORT),
            patch(self._STMT_PORT),
            patch(self._STREAK),
            patch(self._SA_AUDIT),
            patch(self._SA_RAIL),
            patch(self._SA_PORTS),
            patch(self._SA_AGENT) as mock_agent_cls,
        ):
            mock_result = MagicMock()
            mock_result.exit_code = 1  # EXIT_BREACH in agent constants → DISCREPANCY in cron
            mock_result.status_label = "BREACH"
            mock_result.three_leg_result = None
            mock_agent_cls.return_value.run.return_value = mock_result
            exit_code = _run_safeguarding_agent(D, dry_run=True)
        assert exit_code == EXIT_DISCREPANCY

    def test_exception_returns_fatal(self):
        from services.recon.cron_daily_recon import EXIT_FATAL, _run_safeguarding_agent

        # Raise during adapter construction (first lazy import target)
        with patch(self._MIDAZ_PORT, side_effect=RuntimeError("Midaz timeout")):
            exit_code = _run_safeguarding_agent(D, dry_run=True)
        assert exit_code == EXIT_FATAL

    def test_fca_notifier_is_n8n_in_production(self):
        """_run_safeguarding_agent must wire N8nFcaBreachNotifier when not dry_run."""
        from services.recon.cron_daily_recon import _run_safeguarding_agent
        from src.safeguarding.fca_notifier import N8nFcaBreachNotifier

        captured_ports = {}

        def capture_ports(**kwargs):
            captured_ports.update(kwargs)
            m = MagicMock()
            for k, v in kwargs.items():
                setattr(m, k, v)
            return m

        with (
            patch(self._MIDAZ_PORT),
            patch(self._STMT_PORT),
            patch(self._STREAK),
            patch(self._SA_AUDIT),
            patch(self._SA_RAIL),
            patch(self._SA_PORTS, side_effect=capture_ports),
            patch(self._SA_AGENT) as mock_agent_cls,
        ):
            mock_result = MagicMock()
            mock_result.exit_code = 0
            mock_result.status_label = "MATCHED"
            mock_result.three_leg_result = None
            mock_agent_cls.return_value.run.return_value = mock_result
            _run_safeguarding_agent(D, dry_run=False)

        assert isinstance(captured_ports.get("fca_notifier"), N8nFcaBreachNotifier)

    def test_fca_notifier_none_in_dry_run(self):
        """_run_safeguarding_agent must NOT wire notifier in dry_run (sandbox safety)."""
        from services.recon.cron_daily_recon import _run_safeguarding_agent

        captured_ports = {}

        def capture_ports(**kwargs):
            captured_ports.update(kwargs)
            m = MagicMock()
            for k, v in kwargs.items():
                setattr(m, k, v)
            return m

        with (
            patch(self._MIDAZ_PORT),
            patch(self._STMT_PORT),
            patch(self._STREAK),
            patch(self._SA_AUDIT),
            patch(self._SA_RAIL),
            patch(self._SA_PORTS, side_effect=capture_ports),
            patch(self._SA_AGENT) as mock_agent_cls,
        ):
            mock_result = MagicMock()
            mock_result.exit_code = 0
            mock_result.status_label = "MATCHED"
            mock_result.three_leg_result = None
            mock_agent_cls.return_value.run.return_value = mock_result
            _run_safeguarding_agent(D, dry_run=True)

        assert captured_ports.get("fca_notifier") is None
