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
import os
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

CLICKHOUSE_HOST = os.environ.get("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT = int(os.environ.get("CLICKHOUSE_PORT", "9000"))
CLICKHOUSE_DB = os.environ.get("CLICKHOUSE_DB", "banxe")
CLICKHOUSE_USER = os.environ.get("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "")


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
        Create safeguarding_events table if it does not exist.
        Safe to call on every startup (idempotent).
        """
        self._client.execute(_CREATE_TABLE_SQL)
        logger.info("ClickHouse schema ensured: banxe.safeguarding_events")


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
    -- When the reconciliation was performed
    inserted_at     DateTime        DEFAULT now(),
    -- The date being reconciled (not necessarily today)
    recon_date      Date,
    -- Midaz account UUID
    account_id      String,
    -- 'operational' | 'client_funds'
    account_type    LowCardinality(String),
    -- ISO-4217
    currency        LowCardinality(String),
    -- Balance according to Midaz ledger (pence → GBP in Float64 for CH storage)
    internal_balance  Float64,
    -- Balance according to bank statement (CAMT.053 / CSV)
    external_balance  Float64,
    -- external - internal (negative = internal overstates)
    discrepancy       Float64,
    -- 'MATCHED' | 'DISCREPANCY' | 'PENDING'
    status          LowCardinality(String),
    -- Whether an n8n/Slack alert was sent
    alert_sent      UInt8,
    -- Source filename for audit traceability
    source_file     String
)
ENGINE = MergeTree()
ORDER BY (recon_date, account_id)
TTL recon_date + INTERVAL 5 YEAR
SETTINGS index_granularity = 8192;
"""
