"""Unit tests for ADR-032 Step 1: SecretRotationPort + EnvSecretRotator.

Gap ref: G-SEC-01 (secret rotation not defined)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

from services.secrets.env_secret_rotator import EnvSecretRotator


def _make_env_file(tmp_path: Path, content: str) -> Path:
    env_file = tmp_path / ".env"
    env_file.write_text(content)
    return env_file


def test_rotate_generates_new_secret(tmp_path: Path) -> None:
    """Rotation generates a new value different from original."""
    env_file = _make_env_file(tmp_path, "MY_SECRET=old-value-123\nOTHER=keep\n")

    rotator = EnvSecretRotator(
        env_file_path=str(env_file),
        managed_keys=["MY_SECRET"],
        rotation_interval_days=90,
    )
    result = rotator.rotate("MY_SECRET")

    assert result.success is True
    assert result.secret_id == "MY_SECRET"
    assert result.error is None

    # Verify file was updated with new value
    new_content = env_file.read_text()
    assert "old-value-123" not in new_content
    assert "MY_SECRET=" in new_content


def test_rotate_preserves_other_vars(tmp_path: Path) -> None:
    """Rotation of one key does not affect other env vars."""
    env_file = _make_env_file(
        tmp_path, "SECRET_A=aaa\nSECRET_B=bbb\n# comment\nUNMANAGED=keep-me\n"
    )

    rotator = EnvSecretRotator(
        env_file_path=str(env_file),
        managed_keys=["SECRET_A", "SECRET_B"],
        rotation_interval_days=90,
    )
    rotator.rotate("SECRET_A")

    new_content = env_file.read_text()
    assert "SECRET_B=bbb" in new_content
    assert "UNMANAGED=keep-me" in new_content
    assert "# comment" in new_content


def test_rotation_status_not_overdue(tmp_path: Path) -> None:
    """Fresh rotation shows is_overdue=False."""
    env_file = _make_env_file(tmp_path, "KEY=val\n")

    rotator = EnvSecretRotator(
        env_file_path=str(env_file),
        managed_keys=["KEY"],
        rotation_interval_days=90,
    )
    rotator.rotate("KEY")

    status = rotator.get_rotation_status("KEY")
    assert status.is_overdue is False
    assert status.days_until_due > 80
    assert status.last_rotated is not None


def test_rotation_status_overdue(tmp_path: Path) -> None:
    """Secret rotated 91 days ago is overdue."""
    env_file = _make_env_file(tmp_path, "OLD_KEY=val\n")
    state_file = tmp_path / ".rotation-state.json"

    # Write state showing rotation 91 days ago
    old_date = datetime.now(tz=UTC) - timedelta(days=91)
    state_file.write_text(json.dumps({"OLD_KEY": old_date.isoformat()}))

    rotator = EnvSecretRotator(
        env_file_path=str(env_file),
        managed_keys=["OLD_KEY"],
        rotation_interval_days=90,
    )

    status = rotator.get_rotation_status("OLD_KEY")
    assert status.is_overdue is True
    assert status.days_until_due == 0


def test_list_secrets_returns_managed(tmp_path: Path) -> None:
    """list_secrets returns only managed_keys."""
    env_file = _make_env_file(tmp_path, "A=1\nB=2\nC=3\n")

    rotator = EnvSecretRotator(
        env_file_path=str(env_file),
        managed_keys=["A", "B"],
        rotation_interval_days=90,
    )

    secrets_list = rotator.list_secrets()
    assert len(secrets_list) == 2
    ids = [s.secret_id for s in secrets_list]
    assert "A" in ids
    assert "B" in ids
    assert "C" not in ids
    assert all(s.managed is True for s in secrets_list)


def test_check_overdue_returns_only_overdue(tmp_path: Path) -> None:
    """check_overdue filters to only overdue secrets."""
    env_file = _make_env_file(tmp_path, "FRESH=x\nSTALE=y\n")
    state_file = tmp_path / ".rotation-state.json"

    now = datetime.now(tz=UTC)
    state_file.write_text(
        json.dumps(
            {
                "FRESH": now.isoformat(),  # just rotated
                "STALE": (now - timedelta(days=100)).isoformat(),  # overdue
            }
        )
    )

    rotator = EnvSecretRotator(
        env_file_path=str(env_file),
        managed_keys=["FRESH", "STALE"],
        rotation_interval_days=90,
    )

    overdue = rotator.check_overdue()
    assert len(overdue) == 1
    assert overdue[0].secret_id == "STALE"
