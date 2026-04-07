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

import logging
from dataclasses import dataclass
from typing import List, Optional

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
            import clickhouse_driver  # type: ignore
            self._client = clickhouse_driver.Client(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
            )
        except ImportError as exc:
            raise RuntimeError(
                "clickhouse-driver is not installed. "
                "Run: pip install clickhouse-driver"
            ) from exc

    def execute(self, query: str, params: Optional[dict] = None) -> None:
        """
        Execute an INSERT query against ClickHouse.
        Logs every INSERT for audit trail completeness.
        Raises on error — caller (ReconciliationEngine) handles and logs.
        """
        logger.debug("ClickHouseReconClient.execute: query=%s params=%s", query.strip()[:80], params)
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
        self._log: List[_CapturedEvent] = []

    def execute(self, query: str, params: Optional[dict] = None) -> None:
        self._log.append(_CapturedEvent(query=query, params=params or {}))

    @property
    def events(self) -> List[dict]:
        """Return list of param dicts from all INSERT calls."""
        return [e.params for e in self._log]

    @property
    def call_count(self) -> int:
        return len(self._log)

    def reset(self) -> None:
        self._log.clear()


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
