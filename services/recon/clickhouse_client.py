"""
clickhouse_client.py — ClickHouse audit client for safeguarding events
Block J-audit, IL-013 Sprint 9
FCA CASS 15 / I-24 (append-only immutable audit log) | banxe-emi-stack

WHY THIS EXISTS
---------------
ReconciliationEngine requires a ClickHouseClientProtocol to write
safeguarding_events after each daily reconciliation.

This module provides:
  1. ClickHouseReconClient — production client using clickhouse-driver
  2. InMemoryReconClient — in-memory stub for unit tests (no ClickHouse needed)

FCA CASS 15 requirement: audit trail MUST be immutable, append-only,
producible on demand for FCA inspection. ClickHouse is append-only by
design — DELETE/UPDATE are not used. TTL = 5 years (I-15).

Schema: banxe.safeguarding_events (see scripts/schema/clickhouse_safeguarding.sql)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import logging

from services.config import (
    CLICKHOUSE_DB,
    CLICKHOUSE_HOST,
    CLICKHOUSE_PASSWORD,
    CLICKHOUSE_PORT,
    CLICKHOUSE_USER,
)

logger = logging.getLogger(__name__)


class ClickHouseReconClient:
    """
    Production ClickHouse client implementing ClickHouseClientProtocol.

    Writes reconciliation events into banxe.safeguarding_events.
    All inserts are append-only (FCA I-24).

    Prerequisites:
        pip install clickhouse-driver
        Run: scripts/schema/clickhouse_safeguarding.sql on GMKtec ClickHouse
    """

    def __init__(
        self,
        host: str = CLICKHOUSE_HOST,
        port: int = CLICKHOUSE_PORT,
        database: str = CLICKHOUSE_DB,
        user: str = CLICKHOUSE_USER,
        password: str = CLICKHOUSE_PASSWORD,
    ) -> None:
        try:
            import clickhouse_driver  # type: ignore[import-untyped]

            self._client = clickhouse_driver.Client(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
            )
        except ImportError as exc:
            raise RuntimeError(
                "clickhouse-driver is not installed. Run: pip install clickhouse-driver"
            ) from exc

    def execute(self, query: str, params: dict | None = None) -> None:
        """
        Execute an INSERT query against ClickHouse.
        Logs every INSERT for audit trail completeness.
        Raises on error — caller (ReconciliationEngine) handles and logs.
        """
        logger.debug(
            "ClickHouseReconClient.execute: query=%s params=%s", query.strip()[:80], params
        )
        self._client.execute(query, [params] if params else [])

    def ping(self) -> bool:
        """Health check — returns True if ClickHouse is reachable."""
        try:
            self._client.execute("SELECT 1")
            return True
        except Exception as exc:
            logger.warning("ClickHouse ping failed: %s", exc)
            return False

    def ensure_schema(self) -> None:
        """
        Create safeguarding_events and safeguarding_breaches tables if they do not exist.
        Safe to call on every startup — CREATE TABLE IF NOT EXISTS is idempotent.
        NOTE: existing safeguarding_events on GMKtec has compatible schema (Decimal(18,2)).
        """
        self._client.execute(_CREATE_TABLE_SQL)
        self._client.execute(_CREATE_BREACHES_SQL)
        logger.info("ClickHouse schema ensured: safeguarding_events + safeguarding_breaches")

    def get_discrepancy_streak(
        self,
        account_id: str,
        as_of: date,
        min_days: int,  # noqa: F821
    ) -> int:
        """
        Return the number of consecutive DISCREPANCY days for account_id,
        ending on as_of (inclusive). Used by BreachDetector.
        """
        from datetime import timedelta

        rows = self._client.execute(
            """
            SELECT recon_date, status
            FROM banxe.safeguarding_events
            WHERE account_id = %(account_id)s
              AND recon_date >= %(from_date)s
              AND recon_date <= %(as_of)s
            ORDER BY recon_date DESC
            """,
            {
                "account_id": account_id,
                "from_date": (as_of - timedelta(days=min_days + 5)).isoformat(),
                "as_of": as_of.isoformat(),
            },
        )
        streak = 0
        for row in rows or []:
            if row[1] == "DISCREPANCY":
                streak += 1
            else:
                break
        return streak

    def write_breach(self, breach: BreachRecord) -> None:  # noqa: F821
        """Insert one breach record into banxe.safeguarding_breaches."""
        self._client.execute(
            """
            INSERT INTO banxe.safeguarding_breaches
            (recon_date, account_id, account_type, currency,
             discrepancy, days_outstanding)
            VALUES
            """,
            {
                "recon_date": breach.latest_date.isoformat(),
                "account_id": breach.account_id,
                "account_type": breach.account_type,
                "currency": breach.currency,
                "discrepancy": str(breach.discrepancy),
                "days_outstanding": breach.days_outstanding,
            },
        )
        logger.info(
            "Breach written to CH: account=%s days=%d discrepancy=%s",
            breach.account_id,
            breach.days_outstanding,
            breach.discrepancy,
        )

    def get_latest_discrepancy(self, account_id: str, as_of: date) -> dict | None:  # noqa: F821
        """Return most recent DISCREPANCY row for account (for BreachDetector)."""
        rows = self._client.execute(
            """
            SELECT account_id, account_type, currency, discrepancy, recon_date
            FROM banxe.safeguarding_events
            WHERE account_id = %(account_id)s
              AND status = 'DISCREPANCY'
              AND recon_date <= %(as_of)s
            ORDER BY recon_date DESC
            LIMIT 1
            """,
            {"account_id": account_id, "as_of": as_of.isoformat()},
        )
        if not rows:
            return None
        row = rows[0]
        return {
            "account_id": row[0],
            "account_type": row[1],
            "currency": row[2],
            "discrepancy": Decimal(str(row[3])),
            "recon_date": row[4],
        }

    def get_recon_summary(self, date_from: date, date_to: date) -> list[dict]:
        """Return recon status summary for date range (for dashboard API).

        Queries recon_daily_summary materialized view.
        Returns list of dicts with recon_date, status, count, total_discrepancy.
        """
        rows = self._client.execute(
            """
            SELECT recon_date, status, count, total_discrepancy
            FROM banxe.recon_daily_summary
            WHERE recon_date >= %(date_from)s
              AND recon_date <= %(date_to)s
            ORDER BY recon_date DESC, status
            """,
            {"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
        )
        return [
            {
                "recon_date": row[0],
                "status": row[1],
                "count": row[2],
                "total_discrepancy": Decimal(str(row[3])),
            }
            for row in (rows or [])
        ]


@dataclass
class _CapturedEvent:
    """Captured INSERT for InMemoryReconClient inspection in tests."""

    query: str
    params: dict


class InMemoryReconClient:
    """
    In-memory ClickHouse stub for unit tests.

    Records all execute() calls so tests can assert on them
    without a live ClickHouse connection.

    Usage:
        ch = InMemoryReconClient()
        engine = ReconciliationEngine(ledger, ch, fetcher)
        engine.reconcile(date.today())
        assert ch.events[0]["status"] == "MATCHED"
    """

    def __init__(self) -> None:
        self._log: list[_CapturedEvent] = []

    def execute(self, query: str, params: dict | None = None) -> None:
        self._log.append(_CapturedEvent(query=query, params=params or {}))

    @property
    def events(self) -> list[dict]:
        """Return list of param dicts from all INSERT calls."""
        return [e.params for e in self._log]

    @property
    def call_count(self) -> int:
        return len(self._log)

    def reset(self) -> None:
        self._log.clear()

    # ── BreachClientProtocol stubs ────────────────────────────────────────────

    def get_discrepancy_streak(self, account_id: str, as_of, min_days: int) -> int:
        """Stub: count DISCREPANCY events for account in captured log."""
        count = 0
        for e in reversed(self._log):
            if e.params.get("account_id") == account_id and e.params.get("status") == "DISCREPANCY":
                count += 1
            else:
                break
        return count

    def write_breach(self, breach) -> None:
        """Stub: record breach insert in log."""
        self._log.append(
            _CapturedEvent(
                query="BREACH",
                params={
                    "account_id": breach.account_id,
                    "account_type": breach.account_type,
                    "currency": breach.currency,
                    "discrepancy": str(breach.discrepancy),
                    "days_outstanding": breach.days_outstanding,
                    "_is_breach": True,
                },
            )
        )

    def get_latest_discrepancy(self, account_id: str, as_of) -> dict | None:
        """Stub: return last DISCREPANCY event params for account."""
        for e in reversed(self._log):
            if e.params.get("account_id") == account_id and e.params.get("status") == "DISCREPANCY":
                return e.params
        return None

    @property
    def breaches(self) -> list[dict]:
        """Return list of breach param dicts from captured log."""
        return [e.params for e in self._log if e.params.get("_is_breach")]

    def get_recon_summary(self, date_from: date, date_to: date) -> list[dict]:
        """Stub: return summary from captured events grouped by status.

        Groups all captured INSERT events by status and returns counts.
        Used in tests to verify dashboard API data without ClickHouse.
        """
        from collections import defaultdict

        status_counts: dict[str, int] = defaultdict(int)
        status_discrepancy: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

        for e in self._log:
            if e.params.get("_is_breach"):
                continue
            status = e.params.get("status", "")
            recon_date_str = e.params.get("recon_date", "")
            if not status or not recon_date_str:
                continue
            # Filter by date range
            try:
                from datetime import datetime

                recon_date = (
                    datetime.fromisoformat(recon_date_str).date()
                    if isinstance(recon_date_str, str)
                    else recon_date_str
                )
                if date_from <= recon_date <= date_to:
                    status_counts[status] += 1
                    disc = Decimal(str(e.params.get("discrepancy", "0")))
                    status_discrepancy[status] += abs(disc)
            except Exception:
                pass

        return [
            {
                "recon_date": date_to,
                "status": status,
                "count": count,
                "total_discrepancy": status_discrepancy[status],
            }
            for status, count in status_counts.items()
        ]


# ── DDL ──────────────────────────────────────────────────────────────────────

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS banxe.safeguarding_events
(
    -- Unique event ID for deduplication
    event_id         UUID            DEFAULT generateUUIDv4(),
    -- Wall-clock time of reconciliation run (matches existing schema on GMKtec)
    event_time       DateTime64(3)   DEFAULT now(),
    -- The date being reconciled (not necessarily today)
    recon_date       Date,
    -- Midaz account UUID
    account_id       String,
    -- 'operational' | 'client_funds'
    account_type     LowCardinality(String),
    -- ISO-4217
    currency         LowCardinality(String),
    -- Decimal(18,2) — FCA I-24: never float for financial amounts
    internal_balance Decimal(18, 2),
    external_balance Decimal(18, 2),
    discrepancy      Decimal(18, 2),
    -- 'MATCHED' | 'DISCREPANCY' | 'PENDING'
    status           LowCardinality(String),
    -- 1 if n8n/Slack alert was fired
    alert_sent       UInt8           DEFAULT 0,
    -- Statement filename for audit traceability
    source_file      String,
    -- Which service wrote this record
    created_by       String          DEFAULT 'recon-engine'
)
ENGINE = MergeTree()
ORDER BY (recon_date, account_id)
TTL recon_date + INTERVAL 5 YEAR
SETTINGS index_granularity = 8192;
"""

_CREATE_BREACHES_SQL = """
CREATE TABLE IF NOT EXISTS banxe.safeguarding_breaches
(
    detected_at      DateTime        DEFAULT now(),
    recon_date       Date,
    account_id       String,
    account_type     LowCardinality(String),
    currency         LowCardinality(String),
    discrepancy      Decimal(18, 2),
    days_outstanding UInt16          DEFAULT 1,
    reported_to_fca  UInt8           DEFAULT 0,
    notes            String          DEFAULT ''
)
ENGINE = MergeTree()
ORDER BY (detected_at, account_id)
TTL detected_at + INTERVAL 5 YEAR;
"""
