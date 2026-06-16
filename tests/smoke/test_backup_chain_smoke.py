"""End-to-end smoke for the ADR-029 backup chain (Step 5).

Exercises:
  pg_dump (Step 1-3 adapter)         → backup file
  pg_restore + psql (Step 4 adapter) → validation row count
  S3/MinIO upload   (Step 5 adapter) → offsite shipment + listing

without any real subprocess, real database, or real S3. Verifies that the
factory chain wires correctly under env flags.
"""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from services.backup.factory import (
    get_backup_adapter,
    get_offsite_upload_adapter,
    get_restore_drill_adapter,
)
from services.backup.in_memory_offsite_adapter import InMemoryOffsiteAdapter
from services.backup.local_restore_drill_adapter import LocalRestoreDrillAdapter
from services.backup.pg_backup_adapter import PgDumpBackupAdapter

pytestmark = pytest.mark.smoke


class _FakeSubprocessRunner:
    """subprocess.run-shaped fake. Per-command returncodes/stdouts.

    Mirrors the FakeSubprocessRunner used by Step 4 unit tests, scoped here
    so smoke tests are self-contained.
    """

    def __init__(
        self,
        returncodes: dict[str, int] | None = None,
        stdouts: dict[str, str] | None = None,
    ) -> None:
        self._rcs = returncodes or {}
        self._outs = stdouts or {}
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], **_kw: Any) -> subprocess.CompletedProcess:
        self.calls.append(list(args))
        key = args[0]
        return subprocess.CompletedProcess(
            args=args,
            returncode=self._rcs.get(key, 0),
            stdout=self._outs.get(key, ""),
            stderr="",
        )


def test_smoke_backup_then_offsite_upload_full_cycle(tmp_path) -> None:
    """Backup file written locally; offsite adapter ships it and surfaces it."""
    dump_path = tmp_path / "keycloak_20260511_030000.sql.gz"
    dump_path.write_bytes(b"fake-pg-dump-payload" * 200)
    expected_size = dump_path.stat().st_size

    offsite = InMemoryOffsiteAdapter()
    remote_uri = f"s3://banxe-pg-backups/keycloak/{dump_path.name}"

    result = offsite.upload(str(dump_path), remote_uri)
    assert result.success is True
    assert result.remote_uri == remote_uri
    assert result.size_bytes == expected_size
    assert result.error is None

    listed = offsite.list_objects("s3://banxe-pg-backups/keycloak/")
    assert len(listed) == 1
    assert listed[0].uri == remote_uri
    assert listed[0].size_bytes == expected_size


def test_smoke_backup_then_restore_drill_validates(tmp_path) -> None:
    """Drill adapter validates the (mocked) restored DB by row count."""
    # Synthetic backup file — the drill adapter only sees the URI, not contents.
    dump_path = tmp_path / "marble_20260511_030000.sql.gz"
    dump_path.write_bytes(b"x")

    runner = _FakeSubprocessRunner(stdouts={"psql": "  4242  \n"})
    drill = LocalRestoreDrillAdapter(
        subprocess_runner=runner,
        clock=lambda: 1714000000.0,
    )

    result = drill.run_drill(
        instance_name="banxe-marble-postgres",
        backup_uri=str(dump_path),
    )
    assert result.success is True
    assert result.row_count == 4242
    assert result.validation_table == "cases"
    # Cleanup must have been attempted
    invoked = [c[0] for c in runner.calls]
    assert "dropdb" in invoked


def test_smoke_factory_di_resolves_full_backup_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With all three flags enabled, factory resolves the full chain."""
    monkeypatch.setenv("BACKUP_ENABLED", "true")
    monkeypatch.setenv("RESTORE_DRILL_ENABLED", "true")
    monkeypatch.setenv("OFFSITE_UPLOAD_ENABLED", "true")
    monkeypatch.setenv("OFFSITE_UPLOAD_ADAPTER", "in_memory")
    get_restore_drill_adapter.cache_clear()
    get_offsite_upload_adapter.cache_clear()
    try:
        backup = get_backup_adapter()
        drill = get_restore_drill_adapter()
        offsite = get_offsite_upload_adapter()

        assert isinstance(backup, PgDumpBackupAdapter)
        assert isinstance(drill, LocalRestoreDrillAdapter)
        assert isinstance(offsite, InMemoryOffsiteAdapter)
    finally:
        get_restore_drill_adapter.cache_clear()
        get_offsite_upload_adapter.cache_clear()


def test_smoke_offsite_list_objects_returns_uploaded_dump(tmp_path) -> None:
    """Multiple uploads under different prefixes; list_objects round-trips
    with prefix-filter + DESC ordering."""
    offsite = InMemoryOffsiteAdapter(
        clock=iter([1000.0, 1500.0, 2000.0]).__next__,
        file_reader=lambda _p: b"x" * 16,
    )
    # 3 uploads, ascending wall-clock; list_objects must return newest first.
    offsite.upload("/local/a", "s3://banxe-pg-backups/keycloak/a.dump")
    offsite.upload("/local/b", "s3://banxe-pg-backups/clickhouse/b.dump")
    offsite.upload("/local/c", "s3://banxe-pg-backups/keycloak/c.dump")

    kc = offsite.list_objects("s3://banxe-pg-backups/keycloak/")
    assert [o.uri for o in kc] == [
        "s3://banxe-pg-backups/keycloak/c.dump",
        "s3://banxe-pg-backups/keycloak/a.dump",
    ]
    ch = offsite.list_objects("s3://banxe-pg-backups/clickhouse/")
    assert [o.uri for o in ch] == ["s3://banxe-pg-backups/clickhouse/b.dump"]
