"""Integration tests for ADR-032 Step 2: DI wiring + rotation roundtrip.

Gap ref: G-SEC-01 (secret rotation not defined)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from services.secrets.env_secret_rotator import EnvSecretRotator
from services.secrets.factory import SecretRotationDisabledError, get_secret_rotator


def test_factory_creates_rotator_from_env() -> None:
    """Factory returns configured EnvSecretRotator from env vars."""
    env = {
        "SECRET_ROTATION_ENABLED": "true",
        "SECRET_ROTATION_INTERVAL_DAYS": "30",
        "SECRET_ROTATION_MANAGED_KEYS": "KEY_A,KEY_B,KEY_C",
        "SECRET_ROTATION_ENV_FILE": "/tmp/test-secrets.env",
    }
    with patch.dict(os.environ, env, clear=False):
        rotator = get_secret_rotator()

    assert isinstance(rotator, EnvSecretRotator)
    assert rotator._interval_days == 30
    assert rotator._managed_keys == ["KEY_A", "KEY_B", "KEY_C"]
    assert str(rotator._env_path) == "/tmp/test-secrets.env"


def test_factory_disabled_raises() -> None:
    """SECRET_ROTATION_ENABLED=false raises SecretRotationDisabledError."""
    env = {"SECRET_ROTATION_ENABLED": "false"}
    with patch.dict(os.environ, env, clear=False):
        with pytest.raises(SecretRotationDisabledError, match="disabled"):
            get_secret_rotator()


def test_rotate_and_check_status_roundtrip(tmp_path: Path) -> None:
    """Rotate a secret then check status shows fresh (not overdue)."""
    env_file = tmp_path / ".env"
    env_file.write_text("DB_PASSWORD=old-fake-value\n")

    rotator = EnvSecretRotator(
        rotation_interval_days=90,
        env_file_path=str(env_file),
        managed_keys=["DB_PASSWORD"],
    )

    result = rotator.rotate("DB_PASSWORD")
    assert result.success is True

    status = rotator.get_rotation_status("DB_PASSWORD")
    assert status.is_overdue is False
    assert status.last_rotated is not None
    assert status.days_until_due > 80


def test_check_overdue_after_interval(tmp_path: Path) -> None:
    """Secret past interval is detected as overdue."""
    env_file = tmp_path / ".env"
    env_file.write_text("API_KEY=fake-key\nOTHER=val\n")

    state_file = tmp_path / ".rotation-state.json"
    old_date = datetime.now(tz=UTC) - timedelta(days=95)
    state_file.write_text(json.dumps({"API_KEY": old_date.isoformat()}))

    rotator = EnvSecretRotator(
        rotation_interval_days=90,
        env_file_path=str(env_file),
        managed_keys=["API_KEY"],
    )

    overdue = rotator.check_overdue()
    assert len(overdue) == 1
    assert overdue[0].secret_id == "API_KEY"

    status = rotator.get_rotation_status("API_KEY")
    assert status.is_overdue is True
