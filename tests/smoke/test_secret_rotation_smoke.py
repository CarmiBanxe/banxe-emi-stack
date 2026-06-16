"""Smoke tests for ADR-032 Step 3: secret rotation operational readiness.

Gap ref: G-SEC-01 (secret rotation not defined)
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def test_rotation_port_importable() -> None:
    """SecretRotationPort and EnvSecretRotator import without error."""
    from services.secrets.env_secret_rotator import EnvSecretRotator
    from services.secrets.rotation_port import SecretRotationPort

    assert SecretRotationPort is not None
    assert EnvSecretRotator is not None


def test_factory_importable() -> None:
    """get_secret_rotator and SecretRotationConfig import without error."""
    from services.secrets.factory import SecretRotationConfig, get_secret_rotator

    assert get_secret_rotator is not None
    assert SecretRotationConfig is not None


def test_disabled_noop() -> None:
    """SECRET_ROTATION_ENABLED=false causes check script to exit 0 (no-op)."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "secret-rotation-check.py"
    assert script.exists()

    env = os.environ.copy()
    env["SECRET_ROTATION_ENABLED"] = "false"

    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    assert result.returncode == 0
    assert "skipping" in result.stderr.lower()


def test_check_script_exists_and_executable() -> None:
    """scripts/secret-rotation-check.py exists and is executable."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "secret-rotation-check.py"
    assert script.exists(), f"script not found: {script}"
    assert os.access(script, os.X_OK), f"script not executable: {script}"
