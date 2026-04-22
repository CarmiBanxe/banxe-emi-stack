"""
services/audit/pgaudit_config.py — pgAudit configuration and data models
IL-PGA-01 | Phase 51A | Sprint 36
Invariants: I-24 (append-only), I-27 (HITL proposal)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
from typing import Protocol
import uuid

# ── Constants ─────────────────────────────────────────────────────────────────

PGAUDIT_DATABASES: list[str] = ["banxe_compliance", "banxe_core", "banxe_analytics"]

PGAUDIT_SETTINGS: dict[str, str] = {
    "pgaudit.log": "write,ddl",
    "pgaudit.log_parameter": "on",
    "pgaudit.log_catalog": "off",
}

PGAUDIT_VERSION = "1.7"


# ── Data Models ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AuditEntry:
    entry_id: str
    db_name: str
    table_name: str
    operation: str
    actor: str
    timestamp: str
    row_count: int
    success: bool


@dataclass(frozen=True)
class AuditStats:
    db_name: str
    total_writes: int
    total_ddl: int
    last_24h_writes: int
    last_failure: str | None


# ── Protocol (Port) ───────────────────────────────────────────────────────────


class AuditLogPort(Protocol):
    def query(
        self,
        db_name: str,
        table_name: str | None,
        start_date: str,
        end_date: str,
        limit: int,
    ) -> list[AuditEntry]: ...

    def get_stats(self, db_name: str) -> AuditStats: ...


# ── InMemory Adapter (test/sandbox) ──────────────────────────────────────────


class InMemoryAuditLogPort:
    """Append-only in-memory audit log (I-24). Used in tests and sandbox mode."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []
        self._seed_entries()

    def _seed_entries(self) -> None:
        """Seed with representative entries across all databases."""
        seeds = [
            ("banxe_core", "payments", "INSERT", "service_account"),
            ("banxe_core", "accounts", "UPDATE", "api_user"),
            ("banxe_compliance", "aml_cases", "INSERT", "aml_agent"),
            ("banxe_compliance", "sar_reports", "INSERT", "mlro"),
            ("banxe_analytics", "fx_rates", "INSERT", "fx_service"),
        ]
        for db_name, table_name, operation, actor in seeds:
            entry_id = hashlib.sha256(f"{db_name}{table_name}{operation}".encode()).hexdigest()[:8]
            self._entries.append(
                AuditEntry(
                    entry_id=entry_id,
                    db_name=db_name,
                    table_name=table_name,
                    operation=operation,
                    actor=actor,
                    timestamp=datetime.now(UTC).isoformat(),
                    row_count=1,
                    success=True,
                )
            )

    def append(self, entry: AuditEntry) -> None:
        """Append-only. No delete or update (I-24)."""
        self._entries.append(entry)

    def query(
        self,
        db_name: str,
        table_name: str | None,
        start_date: str,
        end_date: str,
        limit: int = 100,
    ) -> list[AuditEntry]:
        results = [e for e in self._entries if e.db_name == db_name]
        if table_name is not None:
            results = [e for e in results if e.table_name == table_name]
        return results[:limit]

    def get_stats(self, db_name: str) -> AuditStats:
        entries = [e for e in self._entries if e.db_name == db_name]
        writes = sum(1 for e in entries if e.operation in ("INSERT", "UPDATE", "DELETE"))
        ddl = sum(1 for e in entries if e.operation in ("CREATE", "ALTER", "DROP"))
        return AuditStats(
            db_name=db_name,
            total_writes=writes,
            total_ddl=ddl,
            last_24h_writes=writes,
            last_failure=None,
        )

    def list_all(self) -> list[AuditEntry]:
        return list(self._entries)

    def add_entry(
        self,
        db_name: str,
        table_name: str,
        operation: str,
        actor: str,
        row_count: int = 1,
        success: bool = True,
    ) -> AuditEntry:
        """Helper to create and append an entry (I-24)."""
        entry_id = hashlib.sha256(f"{uuid.uuid4()}".encode()).hexdigest()[:8]
        entry = AuditEntry(
            entry_id=entry_id,
            db_name=db_name,
            table_name=table_name,
            operation=operation,
            actor=actor,
            timestamp=datetime.now(UTC).isoformat(),
            row_count=row_count,
            success=success,
        )
        self.append(entry)
        return entry
