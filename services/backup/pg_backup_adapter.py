"""PgDumpBackupAdapter — pg_dump/pg_restore implementation of BackupPort (ADR-029).

Designed for cron-driven daily backup of PostgreSQL instances on evo1,
with local retention + evo2 MinIO upload (Step 2 wiring).

Environment variables:
    PG_BACKUP_HOST      PostgreSQL host (default: localhost)
    PG_BACKUP_PORT      PostgreSQL port (default: 5432)
    PG_BACKUP_USER      PostgreSQL user (default: banxe)
    PG_BACKUP_PASSWORD  PostgreSQL password (default: empty)
    PG_BACKUP_DIR       Backup directory (default: /data/banxe/backups)
    PG_BACKUP_RETAIN    Number of backups to keep (default: 7)
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import os
from pathlib import Path
import subprocess

from services.backup.backup_port import (
    BackupMetadata,
    BackupResult,
    RestoreResult,
    RotationResult,
)

logger = logging.getLogger(__name__)


class PgDumpBackupAdapter:
    """Concrete BackupPort implementation using pg_dump/pg_restore."""

    def __init__(
        self,
        *,
        pg_host: str | None = None,
        pg_port: int | None = None,
        pg_user: str | None = None,
        pg_password: str | None = None,
        backup_dir: str | None = None,
        retention_count: int | None = None,
    ) -> None:
        self._pg_host = pg_host or os.getenv("PG_BACKUP_HOST", "localhost")
        self._pg_port = pg_port or int(os.getenv("PG_BACKUP_PORT", "5432"))
        self._pg_user = pg_user or os.getenv("PG_BACKUP_USER", "banxe")
        self._pg_password = pg_password or os.getenv("PG_BACKUP_PASSWORD", "")
        self._backup_dir = Path(backup_dir or os.getenv("PG_BACKUP_DIR", "/data/banxe/backups"))
        self._retention_count = retention_count or int(os.getenv("PG_BACKUP_RETAIN", "7"))

    def backup(self, db_name: str) -> BackupResult:
        """Run pg_dump for the given database."""
        now = datetime.now(tz=UTC)
        filename = f"{db_name}_{now.strftime('%Y%m%d_%H%M%S')}.sql.gz"
        target_dir = self._backup_dir / db_name
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / filename

        env = os.environ.copy()
        if self._pg_password:
            env["PGPASSWORD"] = self._pg_password

        cmd = [
            "pg_dump",
            f"--host={self._pg_host}",
            f"--port={self._pg_port}",
            f"--username={self._pg_user}",
            "--format=custom",
            f"--file={target_path}",
            db_name,
        ]

        try:
            subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            return BackupResult(
                success=False,
                path=str(target_path),
                timestamp=now,
                size_bytes=0,
                error=f"pg_dump failed (exit {exc.returncode}): {exc.stderr[:200]}",
            )

        size = target_path.stat().st_size if target_path.exists() else 0
        logger.info("backup OK: %s (%d bytes)", target_path, size)
        return BackupResult(success=True, path=str(target_path), timestamp=now, size_bytes=size)

    def restore(self, db_name: str, backup_path: str) -> RestoreResult:
        """Run pg_restore for the given database from a backup file."""
        now = datetime.now(tz=UTC)
        path = Path(backup_path)

        if not path.exists():
            return RestoreResult(
                success=False,
                db_name=db_name,
                backup_path=backup_path,
                timestamp=now,
                error=f"backup file not found: {backup_path}",
            )

        env = os.environ.copy()
        if self._pg_password:
            env["PGPASSWORD"] = self._pg_password

        cmd = [
            "pg_restore",
            f"--host={self._pg_host}",
            f"--port={self._pg_port}",
            f"--username={self._pg_user}",
            f"--dbname={db_name}",
            "--clean",
            "--if-exists",
            backup_path,
        ]

        try:
            subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            return RestoreResult(
                success=False,
                db_name=db_name,
                backup_path=backup_path,
                timestamp=now,
                error=f"pg_restore failed (exit {exc.returncode}): {exc.stderr[:200]}",
            )

        logger.info("restore OK: %s -> %s", backup_path, db_name)
        return RestoreResult(success=True, db_name=db_name, backup_path=backup_path, timestamp=now)

    def list_backups(self, db_name: str) -> list[BackupMetadata]:
        """List existing backups for a database, sorted by timestamp descending."""
        target_dir = self._backup_dir / db_name
        if not target_dir.exists():
            return []

        backups: list[BackupMetadata] = []
        for f in target_dir.iterdir():
            if f.is_file() and f.name.startswith(db_name):
                stat = f.stat()
                backups.append(
                    BackupMetadata(
                        path=str(f),
                        db_name=db_name,
                        timestamp=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                        size_bytes=stat.st_size,
                    )
                )

        backups.sort(key=lambda b: b.timestamp, reverse=True)
        return backups

    def rotate(self, db_name: str, keep_last: int | None = None) -> RotationResult:
        """Delete oldest backups, keeping only `keep_last` most recent."""
        keep = keep_last if keep_last is not None else self._retention_count
        backups = self.list_backups(db_name)

        if len(backups) <= keep:
            return RotationResult(success=True, kept=len(backups), deleted=0, freed_bytes=0)

        to_delete = backups[keep:]
        freed = 0
        deleted = 0

        for backup in to_delete:
            try:
                Path(backup.path).unlink()
                freed += backup.size_bytes
                deleted += 1
            except OSError as exc:
                return RotationResult(
                    success=False,
                    kept=keep,
                    deleted=deleted,
                    freed_bytes=freed,
                    error=f"failed to delete {backup.path}: {exc}",
                )

        logger.info("rotation OK: kept=%d deleted=%d freed=%d bytes", keep, deleted, freed)
        return RotationResult(success=True, kept=keep, deleted=deleted, freed_bytes=freed)
