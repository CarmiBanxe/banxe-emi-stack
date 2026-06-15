"""Unit tests for ADR-029 Step 1: BackupPort + PgDumpBackupAdapter.

Gap refs: G-OPS-01 (backup rotation policy) | G-OPS-02 (restore drill)
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import MagicMock, patch

from services.backup.pg_backup_adapter import PgDumpBackupAdapter


def test_backup_creates_file() -> None:
    """pg_dump success returns BackupResult with success=True and valid path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        adapter = PgDumpBackupAdapter(backup_dir=tmpdir)

        with patch("services.backup.pg_backup_adapter.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            # Create the expected file to simulate pg_dump output
            db_dir = Path(tmpdir) / "test_db"
            db_dir.mkdir()

            result = adapter.backup("test_db")

            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert cmd[0] == "pg_dump"
            assert "--format=custom" in cmd
            assert "test_db" in cmd
            assert result.success is True
            assert "test_db" in result.path


def test_backup_failure_returns_error() -> None:
    """pg_dump failure returns BackupResult with success=False and error message."""
    with tempfile.TemporaryDirectory() as tmpdir:
        adapter = PgDumpBackupAdapter(backup_dir=tmpdir)

        with patch("services.backup.pg_backup_adapter.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                1, "pg_dump", stderr="connection refused"
            )

            result = adapter.backup("test_db")

            assert result.success is False
            assert result.error is not None
            assert "pg_dump failed" in result.error
            assert result.size_bytes == 0


def test_restore_success() -> None:
    """pg_restore success returns RestoreResult with success=True."""
    with tempfile.NamedTemporaryFile(suffix=".sql.gz") as tmp:
        adapter = PgDumpBackupAdapter()

        with patch("services.backup.pg_backup_adapter.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = adapter.restore("test_db", tmp.name)

            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert cmd[0] == "pg_restore"
            assert "--dbname=test_db" in cmd
            assert result.success is True
            assert result.db_name == "test_db"
            assert result.backup_path == tmp.name


def test_restore_missing_file_error() -> None:
    """Restore of non-existent file returns error without calling pg_restore."""
    adapter = PgDumpBackupAdapter()

    with patch("services.backup.pg_backup_adapter.subprocess.run") as mock_run:
        result = adapter.restore("test_db", "/nonexistent/path/backup.sql.gz")

        mock_run.assert_not_called()
        assert result.success is False
        assert result.error is not None
        assert "not found" in result.error


def test_list_backups_returns_sorted() -> None:
    """list_backups returns BackupMetadata sorted by timestamp descending."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_dir = Path(tmpdir) / "mydb"
        db_dir.mkdir()

        # Create 3 fake backup files with different mtimes

        for i, name in enumerate(
            ["mydb_20260501.sql.gz", "mydb_20260503.sql.gz", "mydb_20260502.sql.gz"]
        ):
            f = db_dir / name
            f.write_text(f"backup content {i}" * 100)
            # Set mtime: 501, 503, 502
            ts = datetime(2026, 5, 1 + int(name[5:13][-2:]), tzinfo=UTC).timestamp()
            import os

            os.utime(f, (ts, ts))

        adapter = PgDumpBackupAdapter(backup_dir=tmpdir)
        backups = adapter.list_backups("mydb")

        assert len(backups) == 3
        assert backups[0].timestamp >= backups[1].timestamp >= backups[2].timestamp
        assert all(b.db_name == "mydb" for b in backups)
        assert all(b.size_bytes > 0 for b in backups)


def test_rotate_keeps_last_n() -> None:
    """rotate(keep_last=2) deletes oldest backups, keeps 2 most recent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_dir = Path(tmpdir) / "rotdb"
        db_dir.mkdir()

        import os

        # Create 4 backups with different timestamps
        files = []
        for day in [1, 2, 3, 4]:
            f = db_dir / f"rotdb_2026050{day}_060000.sql.gz"
            f.write_text(f"data day {day}" * 50)
            ts = datetime(2026, 5, day, 6, 0, 0, tzinfo=UTC).timestamp()
            os.utime(f, (ts, ts))
            files.append(f)

        adapter = PgDumpBackupAdapter(backup_dir=tmpdir)
        result = adapter.rotate("rotdb", keep_last=2)

        assert result.success is True
        assert result.kept == 2
        assert result.deleted == 2
        assert result.freed_bytes > 0

        # Verify only newest 2 remain
        remaining = list(db_dir.iterdir())
        assert len(remaining) == 2
        remaining_names = sorted(f.name for f in remaining)
        assert "rotdb_20260503_060000.sql.gz" in remaining_names
        assert "rotdb_20260504_060000.sql.gz" in remaining_names
