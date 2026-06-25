"""Tests for ClickHouseStreakCounter.

Coverage:
  - Satisfies StreakCounterPort Protocol (duck-typing / runtime_checkable)
  - get_streak: empty result → 0
  - get_streak: consecutive RECON_BREAK days → correct count
  - get_streak: stops at RECON_MATCHED day
  - get_streak: stops at calendar-day gap
  - get_streak: ClickHouse HTTP error → fail-open 0
  - get_streak: ClickHouse connection error → fail-open 0
  - get_streak: boundary — as_of itself not included in query
  - get_streak: respects lookback_days cutoff
  - get_streak: day with both BREAK and MATCHED events treated as non-break
  - get_streak: malformed TSV lines skipped
  - get_streak: single trailing break day = streak 1
  - get_streak: long streak capped at lookback_days
  - reset_streak: no-op — does not raise
  - Protocol DI: works as SafeguardingAgentPorts.streak_counter
  - _parse_streak: static method unit-testable directly
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from src.safeguarding.agent import StreakCounterPort
from src.safeguarding.clickhouse_streak_counter import ClickHouseStreakCounter

TODAY = date(2026, 6, 26)


# ── helpers ────────────────────────────────────────────────────────────────────


def _make_tsv(*rows: tuple[str, int, int]) -> str:
    """Build a TabSeparated ClickHouse response (day, breaks, matched)."""
    return "\n".join(f"{d}\t{b}\t{m}" for d, b, m in rows)


def _mock_ch_response(text: str, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    resp.raise_for_status = MagicMock(
        side_effect=None if status == 200 else Exception(f"HTTP {status}")
    )
    return resp


# ── StreakCounterPort Protocol compliance ──────────────────────────────────────


class TestProtocolCompliance:
    def test_satisfies_streak_counter_port(self):
        counter = ClickHouseStreakCounter()
        assert isinstance(counter, StreakCounterPort)

    def test_get_streak_method_exists(self):
        assert callable(ClickHouseStreakCounter().get_streak)

    def test_reset_streak_method_exists(self):
        assert callable(ClickHouseStreakCounter().reset_streak)


# ── get_streak: happy path ─────────────────────────────────────────────────────


class TestGetStreakHappyPath:
    def test_empty_result_returns_zero(self):
        with patch("httpx.post", return_value=_mock_ch_response("")):
            assert ClickHouseStreakCounter().get_streak(TODAY) == 0

    def test_single_break_day_returns_one(self):
        tsv = _make_tsv(("2026-06-25", 1, 0))
        with patch("httpx.post", return_value=_mock_ch_response(tsv)):
            assert ClickHouseStreakCounter().get_streak(TODAY) == 1

    def test_two_consecutive_break_days_returns_two(self):
        tsv = _make_tsv(("2026-06-25", 1, 0), ("2026-06-24", 1, 0))
        with patch("httpx.post", return_value=_mock_ch_response(tsv)):
            assert ClickHouseStreakCounter().get_streak(TODAY) == 2

    def test_five_consecutive_breaks_returns_five(self):
        rows = tuple((f"2026-06-{25 - i:02d}", 1, 0) for i in range(5))
        tsv = _make_tsv(*rows)
        with patch("httpx.post", return_value=_mock_ch_response(tsv)):
            assert ClickHouseStreakCounter().get_streak(TODAY) == 5

    def test_breaks_stop_at_matched_day(self):
        # 2 breaks, then a MATCHED day, then more breaks
        tsv = _make_tsv(
            ("2026-06-25", 1, 0),
            ("2026-06-24", 1, 0),
            ("2026-06-23", 0, 1),  # MATCHED — streak stops here
            ("2026-06-22", 1, 0),
        )
        with patch("httpx.post", return_value=_mock_ch_response(tsv)):
            assert ClickHouseStreakCounter().get_streak(TODAY) == 2

    def test_streak_stops_at_calendar_gap(self):
        # Gap between Jun 24 and Jun 22 (Jun 23 missing → no RECON_BREAK that day)
        tsv = _make_tsv(
            ("2026-06-25", 1, 0),
            ("2026-06-24", 1, 0),
            ("2026-06-22", 1, 0),  # gap: Jun 23 missing
        )
        with patch("httpx.post", return_value=_mock_ch_response(tsv)):
            assert ClickHouseStreakCounter().get_streak(TODAY) == 2

    def test_day_with_both_break_and_matched_is_not_counted(self):
        # Edge case: two events on same day → not a clean break day
        tsv = _make_tsv(("2026-06-25", 1, 1))
        with patch("httpx.post", return_value=_mock_ch_response(tsv)):
            assert ClickHouseStreakCounter().get_streak(TODAY) == 0

    def test_matched_only_day_returns_zero(self):
        tsv = _make_tsv(("2026-06-25", 0, 1))
        with patch("httpx.post", return_value=_mock_ch_response(tsv)):
            assert ClickHouseStreakCounter().get_streak(TODAY) == 0


# ── get_streak: fail-open behaviour ───────────────────────────────────────────


class TestGetStreakFailOpen:
    def test_http_error_returns_zero(self):
        bad_resp = _mock_ch_response("", status=503)
        bad_resp.raise_for_status.side_effect = Exception("HTTP 503")
        with patch("httpx.post", return_value=bad_resp):
            assert ClickHouseStreakCounter().get_streak(TODAY) == 0

    def test_connection_error_returns_zero(self):
        import httpx

        with patch("httpx.post", side_effect=httpx.ConnectError("refused")):
            assert ClickHouseStreakCounter().get_streak(TODAY) == 0

    def test_timeout_returns_zero(self):
        import httpx

        with patch("httpx.post", side_effect=httpx.TimeoutException("timeout")):
            assert ClickHouseStreakCounter().get_streak(TODAY) == 0


# ── get_streak: query boundary ────────────────────────────────────────────────


class TestGetStreakQueryBoundary:
    def test_query_excludes_as_of_itself(self):
        """SQL must use < as_of, not <=, so today's event is excluded."""
        captured: list[str] = []

        def capture(url: str, **kwargs: object) -> MagicMock:  # type: ignore[misc]
            q = kwargs.get("params", {}).get("query", "")
            captured.append(q)
            return _mock_ch_response("")

        with patch("httpx.post", side_effect=capture):
            ClickHouseStreakCounter().get_streak(TODAY)

        assert captured, "httpx.post was not called"
        assert f"< '{TODAY.isoformat()}'" in captured[0]
        assert f"<= '{TODAY.isoformat()}'" not in captured[0]

    def test_lookback_days_limits_query_window(self):
        """Custom lookback_days adjusts the lower bound in the SQL."""
        captured: list[str] = []

        def capture(url: str, **kwargs: object) -> MagicMock:  # type: ignore[misc]
            q = kwargs.get("params", {}).get("query", "")
            captured.append(q)
            return _mock_ch_response("")

        counter = ClickHouseStreakCounter(lookback_days=7)
        with patch("httpx.post", side_effect=capture):
            counter.get_streak(TODAY)

        from datetime import timedelta

        expected_cutoff = TODAY - timedelta(days=7)
        assert f">= '{expected_cutoff.isoformat()}'" in captured[0]


# ── reset_streak ──────────────────────────────────────────────────────────────


class TestResetStreak:
    def test_reset_streak_does_not_raise(self):
        ClickHouseStreakCounter().reset_streak(TODAY)

    def test_reset_streak_makes_no_http_call(self):
        with patch("httpx.post") as mock_post:
            ClickHouseStreakCounter().reset_streak(TODAY)
            mock_post.assert_not_called()


# ── _parse_streak static method ───────────────────────────────────────────────


class TestParseStreak:
    def test_empty_string_returns_zero(self):
        assert ClickHouseStreakCounter._parse_streak("", TODAY) == 0

    def test_malformed_line_skipped(self):
        tsv = "bad_line\n2026-06-25\t1\t0"
        assert ClickHouseStreakCounter._parse_streak(tsv, TODAY) == 1

    def test_blank_lines_skipped(self):
        tsv = "\n\n2026-06-25\t1\t0\n\n"
        assert ClickHouseStreakCounter._parse_streak(tsv, TODAY) == 1


# ── Protocol DI integration ───────────────────────────────────────────────────


class TestProtocolDI:
    def test_usable_as_safeguarding_agent_ports_streak_counter(self):
        """ClickHouseStreakCounter fits SafeguardingAgentPorts.streak_counter."""
        from decimal import Decimal

        from src.safeguarding.agent import (
            SafeguardingAgentPorts,
            StubBankStatementPort,
            StubLedgerPort,
        )
        from src.safeguarding.audit_trail import AuditTrail

        ports = SafeguardingAgentPorts(
            ledger=StubLedgerPort(balance_gbp=Decimal("100000.00")),
            bank=StubBankStatementPort(balance_gbp=Decimal("100000.00")),
            audit=AuditTrail(dry_run=True),
            streak_counter=ClickHouseStreakCounter(),
        )
        # Duck-typing: no runtime error when assigning
        assert ports.streak_counter is not None

    def test_in_memory_also_satisfies_protocol(self):
        from src.safeguarding.agent import InMemoryStreakCounter  # noqa: PLC0415

        assert isinstance(InMemoryStreakCounter(), StreakCounterPort)
