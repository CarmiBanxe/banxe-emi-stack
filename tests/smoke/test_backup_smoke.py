"""Smoke tests for ADR-029 Step 3: Postgres backup operational readiness.

Gap refs: G-OPS-01 (backup rotation policy) | G-OPS-02 (restore drill)
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


def test_backup_port_importable() -> None:
    """BackupPort and PgDumpBackupAdapter import without error."""
    from services.backup.backup_port import BackupPort
    from services.backup.pg_backup_adapter import PgDumpBackupAdapter

    assert BackupPort is not None
    assert PgDumpBackupAdapter is not None


def test_factory_importable_and_config_from_env() -> None:
    """get_backup_adapter and BackupConfig.from_env() work with mock env."""
    from services.backup.factory import BackupConfig

    env = {
        "BACKUP_ENABLED": "true",
        "BACKUP_PG_HOST": "test-host",
        "BACKUP_PG_PORT": "5433",
        "BACKUP_PG_USER": "testuser",
        "BACKUP_PG_PASSWORD": "testpass",
        "BACKUP_DIR": "/tmp/smoke-backups",
        "BACKUP_RETENTION_COUNT": "3",
    }
    with patch.dict(os.environ, env, clear=False):
        config = BackupConfig.from_env()

    assert config.enabled is True
    assert config.pg_host == "test-host"
    assert config.pg_port == 5433
    assert config.retention_count == 3


def test_backup_disabled_flag_noop() -> None:
    """BACKUP_ENABLED=false causes cron script to exit 0 (no-op)."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "pg-backup-run.py"
    assert script.exists()

    env = os.environ.copy()
    env["BACKUP_ENABLED"] = "false"

    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    assert result.returncode == 0
    assert "skipping" in result.stderr.lower() or "no-op" in result.stderr.lower()


def test_cron_script_exists_and_executable() -> None:
    """scripts/pg-backup-run.py exists and is executable."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "pg-backup-run.py"
    assert script.exists(), f"script not found: {script}"
    assert os.access(script, os.X_OK), f"script not executable: {script}"
