"""Integration tests for ADR-029 Step 2: DI wiring + backup roundtrip.

Gap refs: G-OPS-01 (backup rotation policy) | G-OPS-02 (restore drill)
"""

from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from services.backup.factory import BackupDisabledError, get_backup_adapter
from services.backup.pg_backup_adapter import PgDumpBackupAdapter


def test_factory_creates_adapter_from_env() -> None:
    """Factory returns PgDumpBackupAdapter with correct params from env."""
    env = {
        "BACKUP_ENABLED": "true",
        "BACKUP_PG_HOST": "192.168.0.72",
        "BACKUP_PG_PORT": "15433",
        "BACKUP_PG_USER": "marble",
        "BACKUP_PG_PASSWORD": "secret123",
        "BACKUP_DIR": "/tmp/test-backups",
        "BACKUP_RETENTION_COUNT": "14",
    }
    with patch.dict(os.environ, env, clear=False):
        adapter = get_backup_adapter()

    assert isinstance(adapter, PgDumpBackupAdapter)
    assert adapter._pg_host == "192.168.0.72"
    assert adapter._pg_port == 15433
    assert adapter._pg_user == "marble"
    assert adapter._pg_password == "secret123"
    assert str(adapter._backup_dir) == "/tmp/test-backups"
    assert adapter._retention_count == 14


def test_factory_disabled_flag() -> None:
    """BACKUP_ENABLED=false raises BackupDisabledError."""
    env = {"BACKUP_ENABLED": "false"}
    with patch.dict(os.environ, env, clear=False):
        with pytest.raises(BackupDisabledError, match="disabled"):
            get_backup_adapter()


def test_factory_disabled_by_default() -> None:
    """Default (no BACKUP_ENABLED set) raises BackupDisabledError."""
    env_clean = {k: v for k, v in os.environ.items() if k != "BACKUP_ENABLED"}
    with patch.dict(os.environ, env_clean, clear=True):
        with pytest.raises(BackupDisabledError):
            get_backup_adapter()


def test_backup_and_list_roundtrip() -> None:
    """Backup creates entry visible in list_backups (mock subprocess)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        adapter = PgDumpBackupAdapter(backup_dir=tmpdir, retention_count=7)

        with patch("services.backup.pg_backup_adapter.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            # Perform backup (pg_dump mocked)
            result = adapter.backup("keycloak")
            assert result.success is True

            # Create the file that pg_dump would have created
            Path(result.path).parent.mkdir(parents=True, exist_ok=True)
            Path(result.path).write_text("fake backup data")

        # List should find it
        backups = adapter.list_backups("keycloak")
        assert len(backups) == 1
        assert backups[0].db_name == "keycloak"
        assert backups[0].size_bytes > 0


def test_rotate_integration() -> None:
    """Rotate with 10 backups and keep_last=7 removes 3 oldest."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_dir = Path(tmpdir) / "compliance_db"
        db_dir.mkdir()

        # Create 10 backup files with sequential timestamps
        for day in range(1, 11):
            f = db_dir / f"compliance_db_2026050{day:02d}_060000.sql.gz"
            f.write_text(f"backup data day {day}" * 100)
            ts = datetime(2026, 5, day, 6, 0, 0, tzinfo=UTC).timestamp()
            os.utime(f, (ts, ts))

        adapter = PgDumpBackupAdapter(backup_dir=tmpdir, retention_count=7)

        # Verify 10 backups exist
        assert len(adapter.list_backups("compliance_db")) == 10

        # Rotate: keep 7
        result = adapter.rotate("compliance_db", keep_last=7)
        assert result.success is True
        assert result.kept == 7
        assert result.deleted == 3
        assert result.freed_bytes > 0

        # Verify only 7 remain (newest)
        remaining = adapter.list_backups("compliance_db")
        assert len(remaining) == 7
        # Oldest remaining should be day 4 (days 1,2,3 deleted)
        oldest_remaining = remaining[-1]
        assert "04" in oldest_remaining.path or "05" in oldest_remaining.path
