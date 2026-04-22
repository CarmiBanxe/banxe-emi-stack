"""
tests/test_audit/test_pgaudit_config.py — pgAudit config and InMemoryAuditLogPort tests
IL-PGA-01 | Phase 51A | Sprint 36
≥20 tests covering constants, AuditEntry, AuditStats, InMemoryAuditLogPort
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from services.audit.pgaudit_config import (
    PGAUDIT_DATABASES,
    PGAUDIT_SETTINGS,
    AuditEntry,
    AuditStats,
    InMemoryAuditLogPort,
)

# ── PGAUDIT_DATABASES ─────────────────────────────────────────────────────────


def test_pgaudit_databases_is_list() -> None:
    assert isinstance(PGAUDIT_DATABASES, list)


def test_pgaudit_databases_has_three() -> None:
    assert len(PGAUDIT_DATABASES) == 3


def test_pgaudit_databases_contains_core() -> None:
    assert "banxe_core" in PGAUDIT_DATABASES


def test_pgaudit_databases_contains_compliance() -> None:
    assert "banxe_compliance" in PGAUDIT_DATABASES


def test_pgaudit_databases_contains_analytics() -> None:
    assert "banxe_analytics" in PGAUDIT_DATABASES


# ── PGAUDIT_SETTINGS ──────────────────────────────────────────────────────────


def test_pgaudit_settings_is_dict() -> None:
    assert isinstance(PGAUDIT_SETTINGS, dict)


def test_pgaudit_settings_has_log_key() -> None:
    assert "pgaudit.log" in PGAUDIT_SETTINGS


def test_pgaudit_settings_log_value() -> None:
    assert PGAUDIT_SETTINGS["pgaudit.log"] == "write,ddl"


def test_pgaudit_settings_log_parameter() -> None:
    assert "pgaudit.log_parameter" in PGAUDIT_SETTINGS


# ── AuditEntry ────────────────────────────────────────────────────────────────


def test_audit_entry_is_frozen() -> None:
    entry = AuditEntry(
        entry_id="abc12345",
        db_name="banxe_core",
        table_name="payments",
        operation="INSERT",
        actor="service",
        timestamp=datetime.now(UTC).isoformat(),
        row_count=1,
        success=True,
    )
    with pytest.raises(FrozenInstanceError):
        entry.success = False  # type: ignore[misc]


def test_audit_entry_fields() -> None:
    entry = AuditEntry(
        entry_id="abc12345",
        db_name="banxe_core",
        table_name="payments",
        operation="INSERT",
        actor="service",
        timestamp="2026-04-21T00:00:00+00:00",
        row_count=1,
        success=True,
    )
    assert entry.db_name == "banxe_core"
    assert entry.operation == "INSERT"
    assert entry.success is True


# ── AuditStats ────────────────────────────────────────────────────────────────


def test_audit_stats_is_frozen() -> None:
    stats = AuditStats(
        db_name="banxe_core",
        total_writes=10,
        total_ddl=2,
        last_24h_writes=3,
        last_failure=None,
    )
    with pytest.raises(FrozenInstanceError):
        stats.total_writes = 99  # type: ignore[misc]


def test_audit_stats_last_failure_none() -> None:
    stats = AuditStats("banxe_core", 10, 2, 3, None)
    assert stats.last_failure is None


# ── InMemoryAuditLogPort ──────────────────────────────────────────────────────


def test_in_memory_port_seeded() -> None:
    port = InMemoryAuditLogPort()
    assert len(port.list_all()) == 5


def test_in_memory_port_seeds_across_dbs() -> None:
    port = InMemoryAuditLogPort()
    dbs = {e.db_name for e in port.list_all()}
    assert "banxe_core" in dbs
    assert "banxe_compliance" in dbs
    assert "banxe_analytics" in dbs


def test_in_memory_port_query_by_db() -> None:
    port = InMemoryAuditLogPort()
    entries = port.query("banxe_core", None, "2020-01-01", "2099-12-31", 100)
    for e in entries:
        assert e.db_name == "banxe_core"


def test_in_memory_port_query_by_table() -> None:
    port = InMemoryAuditLogPort()
    entries = port.query("banxe_core", "payments", "2020-01-01", "2099-12-31", 100)
    for e in entries:
        assert e.table_name == "payments"


def test_in_memory_port_query_limit() -> None:
    port = InMemoryAuditLogPort()
    entries = port.query("banxe_core", None, "2020-01-01", "2099-12-31", 1)
    assert len(entries) <= 1


def test_in_memory_port_append_increases_count() -> None:
    port = InMemoryAuditLogPort()
    initial = len(port.list_all())
    entry = AuditEntry(
        entry_id="new001",
        db_name="banxe_core",
        table_name="accounts",
        operation="INSERT",
        actor="test",
        timestamp=datetime.now(UTC).isoformat(),
        row_count=1,
        success=True,
    )
    port.append(entry)
    assert len(port.list_all()) == initial + 1


def test_in_memory_port_has_no_delete() -> None:
    port = InMemoryAuditLogPort()
    assert not hasattr(port, "delete")
    assert not hasattr(port, "remove")


def test_in_memory_port_get_stats_writes() -> None:
    port = InMemoryAuditLogPort()
    stats = port.get_stats("banxe_core")
    assert stats.total_writes >= 0


def test_in_memory_port_get_stats_db_name() -> None:
    port = InMemoryAuditLogPort()
    stats = port.get_stats("banxe_compliance")
    assert stats.db_name == "banxe_compliance"


def test_in_memory_port_add_entry_helper() -> None:
    port = InMemoryAuditLogPort()
    initial = len(port.list_all())
    entry = port.add_entry("banxe_analytics", "fx_rates", "INSERT", "fx_service")
    assert entry.db_name == "banxe_analytics"
    assert len(port.list_all()) == initial + 1


def test_in_memory_port_entry_id_8chars() -> None:
    port = InMemoryAuditLogPort()
    entry = port.add_entry("banxe_core", "payments", "INSERT", "svc")
    assert len(entry.entry_id) == 8
