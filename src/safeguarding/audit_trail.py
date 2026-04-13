"""Audit trail — ClickHouse immutable append-only event log.

Satisfies:
  I-21: 5-year (+ 1 year buffer) TTL for all compliance events
  CASS 15 / SYSC 9: Regulatory record-keeping
  EU AI Act Art.17: High-risk AI system logging

ClickHouse table (create once):
  CREATE TABLE IF NOT EXISTS banxe.safeguarding_audit
  (
      event_id     UUID DEFAULT generateUUIDv4(),
      event_type   LowCardinality(String),
      occurred_at  DateTime64(3, 'UTC'),
      entity_id    String,
      actor        String,
      payload      String,    -- JSON
      severity     LowCardinality(String),
      _ingested_at DateTime64(3, 'UTC') DEFAULT now64()
  )
  ENGINE = MergeTree
  PARTITION BY toYYYYMM(occurred_at)
  ORDER BY (occurred_at, event_type, entity_id)
  TTL occurred_at + INTERVAL 6 YEAR DELETE
  SETTINGS index_granularity = 8192;

If ClickHouse is unavailable the trail falls back to stderr (fail-open
logging, not fail-closed) so that compliance events are NEVER silently dropped.

Usage:
    trail = AuditTrail(clickhouse_url="http://localhost:8123",
                       database="banxe", dry_run=False)
    trail.log(AuditEvent(
        event_type="RECON_BREAK",
        entity_id="recon-2026-04-13",
        actor="DailyReconciliation",
        payload={"diff_gbp": "50.00"},
        severity="CRITICAL",
    ))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import logging
from typing import Any
import uuid

logger = logging.getLogger(__name__)

# ClickHouse INSERT template — parameterised via VALUES
_INSERT_SQL = (
    "INSERT INTO {database}.safeguarding_audit "
    "(event_id, event_type, occurred_at, entity_id, actor, payload, severity) "
    "VALUES"
)


@dataclass
class AuditEvent:
    """A single immutable audit record.

    Args:
        event_type: Slug identifying the event class, e.g. RECON_BREAK,
                    BREACH_DETECTED, FIN060_SUBMITTED, SHORTFALL_ALERT.
        entity_id:  ID of the primary entity (reconciliation ID, breach ID, etc.)
        actor:      Module or human that triggered the event.
        payload:    Arbitrary key-value data (must be JSON-serialisable).
        severity:   INFO | WARNING | MAJOR | CRITICAL
    """

    event_type: str
    entity_id: str
    actor: str
    payload: dict[str, Any] = field(default_factory=dict)
    severity: str = "INFO"
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def payload_json(self) -> str:
        return json.dumps(self.payload, default=str)


class AuditTrail:
    """Append-only writer for the ClickHouse safeguarding_audit table.

    Args:
        clickhouse_url: Base URL of ClickHouse HTTP interface,
                        e.g. "http://localhost:8123".
        database:       ClickHouse database name (default: "banxe").
        dry_run:        If True, log to stdout only — no ClickHouse writes.
                        Use in tests and local dev.
        clickhouse_user: ClickHouse username (default: "default").
        clickhouse_password: ClickHouse password (default: "").
    """

    def __init__(
        self,
        clickhouse_url: str = "http://localhost:8123",
        database: str = "banxe",
        dry_run: bool = True,
        clickhouse_user: str = "default",
        clickhouse_password: str = "",
    ) -> None:
        self.clickhouse_url = clickhouse_url.rstrip("/")
        self.database = database
        self.dry_run = dry_run
        self.user = clickhouse_user
        self.password = clickhouse_password
        self._ch_available: bool | None = None  # cached connection check

    def log(self, event: AuditEvent) -> bool:
        """Append an audit event. Returns True on success.

        Never raises — compliance events must not crash the caller.
        Falls back to stderr logging if ClickHouse is unreachable.
        """
        try:
            return self._write(event)
        except Exception as exc:
            logger.error(
                "AuditTrail FALLBACK — ClickHouse write failed (%s). "
                "Event logged to stderr: event_id=%s type=%s entity=%s severity=%s payload=%s",
                exc,
                event.event_id,
                event.event_type,
                event.entity_id,
                event.severity,
                event.payload_json(),
            )
            return False

    def _write(self, event: AuditEvent) -> bool:
        if self.dry_run:
            logger.info(
                "AuditTrail DRY_RUN: event_id=%s type=%s entity=%s severity=%s payload=%s",
                event.event_id,
                event.event_type,
                event.entity_id,
                event.severity,
                event.payload_json(),
            )
            return True

        try:
            import httpx
        except ImportError:
            logger.error("AuditTrail: httpx not installed — falling back to stderr logging.")
            logger.critical(
                "AUDIT EVENT (no-ch): id=%s type=%s entity=%s severity=%s",
                event.event_id,
                event.event_type,
                event.entity_id,
                event.severity,
            )
            return False

        row = (
            f"('{event.event_id}', '{event.event_type}', "
            f"'{event.occurred_at.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}', "
            f"'{event.entity_id}', '{event.actor}', "
            f"'{event.payload_json().replace(chr(39), chr(39) * 2)}', "
            f"'{event.severity}')"
        )
        sql = _INSERT_SQL.format(database=self.database) + " " + row

        resp = httpx.post(
            self.clickhouse_url,
            params={"query": sql},
            auth=(self.user, self.password) if self.password else None,
            timeout=5.0,
        )
        resp.raise_for_status()
        return True

    def ensure_table(self) -> None:
        """Create the ClickHouse audit table if it does not exist.

        Call once at service start-up (idempotent).
        No-ops in dry_run mode.
        """
        if self.dry_run:
            logger.info("AuditTrail DRY_RUN: skipping ensure_table")
            return

        try:
            import httpx
        except ImportError:
            logger.warning("AuditTrail: httpx not installed — cannot create table.")
            return

        ddl = f"""
        CREATE TABLE IF NOT EXISTS {self.database}.safeguarding_audit
        (
            event_id     UUID DEFAULT generateUUIDv4(),
            event_type   LowCardinality(String),
            occurred_at  DateTime64(3, 'UTC'),
            entity_id    String,
            actor        String,
            payload      String,
            severity     LowCardinality(String),
            _ingested_at DateTime64(3, 'UTC') DEFAULT now64()
        )
        ENGINE = MergeTree
        PARTITION BY toYYYYMM(occurred_at)
        ORDER BY (occurred_at, event_type, entity_id)
        TTL occurred_at + INTERVAL 6 YEAR DELETE
        SETTINGS index_granularity = 8192
        """.strip()

        try:
            resp = httpx.post(
                self.clickhouse_url,
                params={"query": ddl},
                auth=(self.user, self.password) if self.password else None,
                timeout=10.0,
            )
            resp.raise_for_status()
            logger.info(
                "AuditTrail: safeguarding_audit table ensured in %s.%s",
                self.clickhouse_url,
                self.database,
            )
        except Exception as exc:
            logger.error("AuditTrail: failed to ensure table — %s", exc)
