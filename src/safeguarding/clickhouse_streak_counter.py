"""clickhouse_streak_counter.py — ClickHouse-backed StreakCounterPort.

Queries the safeguarding_audit table for consecutive RECON_BREAK events
going backward from (as_of - 1 day) to compute the break streak passed
to BreachDetector on each daily run.

Called by SafeguardingAgent._run_internal() before today's audit event
is written, so the query boundary is strictly < as_of (yesterday and earlier).

Fail-open: returns 0 on ClickHouse failure.  The audit trail still captures
every RECON_BREAK event — streak is always recoverable from history.

FCA reference: CASS 7.15.29G / PS23/3 §3.49 (streak-based breach notification).

Usage:
    from src.safeguarding.clickhouse_streak_counter import ClickHouseStreakCounter

    counter = ClickHouseStreakCounter(
        clickhouse_url="http://localhost:8123",
        database="banxe",
    )
    streak = counter.get_streak(date.today())
"""

from __future__ import annotations

from datetime import date, timedelta
import logging

logger = logging.getLogger(__name__)

_LOOKBACK_DAYS_DEFAULT = 30
_CH_TIMEOUT = 5.0


class ClickHouseStreakCounter:
    """ClickHouse-backed streak counter for CASS 15 consecutive reconciliation breaks.

    Queries ``{database}.safeguarding_audit`` for consecutive ``RECON_BREAK``
    days immediately before ``as_of``.  Today's audit event has not yet been
    written when ``get_streak`` is called from SafeguardingAgent, so the query
    uses a strict ``< as_of`` boundary.

    ``reset_streak`` is a no-op: the RECON_MATCHED audit event written by
    AuditTrail already acts as the natural streak-reset sentinel on the next
    call to ``get_streak``.

    Args:
        clickhouse_url: Base URL of ClickHouse HTTP interface, e.g.
                        ``"http://localhost:8123"``.
        database:       ClickHouse database (default: ``"banxe"``).
        clickhouse_user:     ClickHouse username (default: ``"default"``).
        clickhouse_password: ClickHouse password (default: ``""``).
        lookback_days:  Max calendar days to scan for consecutive breaks
                        (default: 30).  Caps the query window; a break
                        streak longer than this returns ``lookback_days``.
    """

    def __init__(
        self,
        clickhouse_url: str = "http://localhost:8123",
        database: str = "banxe",
        clickhouse_user: str = "default",
        clickhouse_password: str = "",
        lookback_days: int = _LOOKBACK_DAYS_DEFAULT,
    ) -> None:
        self._url = clickhouse_url.rstrip("/")
        self._db = database
        self._user = clickhouse_user
        self._password = clickhouse_password
        self._lookback = max(1, lookback_days)

    # ── Public interface (StreakCounterPort) ───────────────────────────────────

    def get_streak(self, as_of: date) -> int:
        """Count consecutive RECON_BREAK days immediately before *as_of*.

        Returns 0 on any ClickHouse error (fail-open, conservative for breach
        detection — individual RECON_BREAK events are preserved in audit trail).
        """
        try:
            return self._query_streak(as_of)
        except Exception as exc:
            logger.error(
                "ClickHouseStreakCounter.get_streak(%s) failed — %s. Returning 0 (fail-open).",
                as_of.isoformat(),
                exc,
            )
            return 0

    def reset_streak(self, as_of: date) -> None:
        """No-op.

        The RECON_MATCHED audit event written by AuditTrail on the same day
        breaks the streak naturally: the next ``get_streak`` call will encounter
        that MATCHED event and stop counting.
        """
        logger.debug("ClickHouseStreakCounter.reset_streak no-op for %s", as_of.isoformat())

    # ── Internal ──────────────────────────────────────────────────────────────

    def _query_streak(self, as_of: date) -> int:
        """Query ClickHouse and walk backward through days counting breaks."""
        import httpx

        cutoff = as_of - timedelta(days=self._lookback)
        # db name from config; dates from .isoformat() (no injection risk)
        sql = (
            f"SELECT toDate(occurred_at) AS recon_day, "  # noqa: S608
            f"countIf(event_type = 'RECON_BREAK') AS breaks, "
            f"countIf(event_type = 'RECON_MATCHED') AS matched "
            f"FROM {self._db}.safeguarding_audit "
            f"WHERE toDate(occurred_at) < '{as_of.isoformat()}' "
            f"AND toDate(occurred_at) >= '{cutoff.isoformat()}' "
            f"AND actor = 'SafeguardingAgent' "
            f"GROUP BY recon_day "
            f"ORDER BY recon_day DESC "
            f"FORMAT TabSeparated"
        )
        resp = httpx.post(
            self._url,
            params={"query": sql},
            auth=(self._user, self._password) if self._password else None,
            timeout=_CH_TIMEOUT,
        )
        resp.raise_for_status()
        return self._parse_streak(resp.text, as_of)

    @staticmethod
    def _parse_streak(tsv: str, as_of: date) -> int:
        """Walk rows (newest first) counting consecutive RECON_BREAK-only days."""
        streak = 0
        prev_day: date | None = None

        for line in tsv.strip().splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 3:  # noqa: PLR2004
                continue
            try:
                day = date.fromisoformat(parts[0])
                breaks = int(parts[1])
                matched = int(parts[2])
            except (ValueError, IndexError):
                continue

            # A gap in calendar days (missed day = no RECON_BREAK) breaks the streak
            if prev_day is not None and (prev_day - day).days > 1:
                break
            prev_day = day

            if breaks > 0 and matched == 0:
                streak += 1
            else:
                # Day had a MATCHED event (or no BREAK) — streak ends
                break

        return streak
