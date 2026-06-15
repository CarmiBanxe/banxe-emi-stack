"""EnvSecretRotator — .env-based secret rotation (ADR-032, G-SEC-01).

Rotates secrets stored in .env files by generating new values via
secrets.token_urlsafe(32) and updating the file in place.

Rotation metadata (timestamps) stored in a companion .rotation-state.json
file alongside the .env to track last-rotated dates without exposing values.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import logging
from pathlib import Path
import secrets

from services.secrets.rotation_port import (
    RotationResult,
    RotationStatus,
    SecretMetadata,
)

logger = logging.getLogger(__name__)


class EnvSecretRotator:
    """Concrete SecretRotationPort for .env file-based secrets."""

    def __init__(
        self,
        *,
        rotation_interval_days: int = 90,
        env_file_path: str = ".env",
        managed_keys: list[str] | None = None,
    ) -> None:
        self._interval_days = rotation_interval_days
        self._env_path = Path(env_file_path)
        self._managed_keys = managed_keys or []
        self._state_path = self._env_path.parent / ".rotation-state.json"
        self._state: dict[str, str] = self._load_state()

    def _load_state(self) -> dict[str, str]:
        """Load rotation state (last-rotated timestamps) from companion file."""
        if self._state_path.exists():
            return json.loads(self._state_path.read_text())
        return {}

    def _save_state(self) -> None:
        """Persist rotation state."""
        self._state_path.write_text(json.dumps(self._state, indent=2))

    def _read_env(self) -> dict[str, str]:
        """Parse .env file into key=value dict."""
        if not self._env_path.exists():
            return {}
        result: dict[str, str] = {}
        for line in self._env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
        return result

    def _write_env(self, data: dict[str, str]) -> None:
        """Write key=value pairs back to .env file, preserving comments."""
        lines: list[str] = []
        if self._env_path.exists():
            for line in self._env_path.read_text().splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    key = stripped.partition("=")[0].strip()
                    if key in data:
                        lines.append(f"{key}={data[key]}")
                        continue
                lines.append(line)
        else:
            for key, value in data.items():
                lines.append(f"{key}={value}")
        self._env_path.write_text("\n".join(lines) + "\n")

    def rotate(self, secret_id: str) -> RotationResult:
        """Generate a new secret value and update the .env file."""
        now = datetime.now(tz=UTC)

        if secret_id not in self._managed_keys:
            return RotationResult(
                success=False,
                secret_id=secret_id,
                rotated_at=now,
                next_due=now,
                error=f"secret_id '{secret_id}' not in managed_keys",
            )

        env_data = self._read_env()
        new_value = secrets.token_urlsafe(32)
        env_data[secret_id] = new_value
        self._write_env(env_data)

        self._state[secret_id] = now.isoformat()
        self._save_state()

        next_due = now + timedelta(days=self._interval_days)
        logger.info("rotated secret %s (next due: %s)", secret_id, next_due.date())
        return RotationResult(success=True, secret_id=secret_id, rotated_at=now, next_due=next_due)

    def get_rotation_status(self, secret_id: str) -> RotationStatus:
        """Get rotation status for a specific secret."""
        now = datetime.now(tz=UTC)
        last_str = self._state.get(secret_id)
        last_rotated = datetime.fromisoformat(last_str) if last_str else None

        if last_rotated is None:
            return RotationStatus(
                secret_id=secret_id,
                last_rotated=None,
                next_due=None,
                is_overdue=True,
                days_until_due=0,
            )

        next_due = last_rotated + timedelta(days=self._interval_days)
        days_until = (next_due - now).days
        is_overdue = days_until < 0

        return RotationStatus(
            secret_id=secret_id,
            last_rotated=last_rotated,
            next_due=next_due,
            is_overdue=is_overdue,
            days_until_due=max(0, days_until),
        )

    def list_secrets(self) -> list[SecretMetadata]:
        """List all managed secrets with metadata."""
        result: list[SecretMetadata] = []
        for key in self._managed_keys:
            last_str = self._state.get(key)
            last_rotated = datetime.fromisoformat(last_str) if last_str else None
            result.append(
                SecretMetadata(
                    secret_id=key,
                    managed=True,
                    last_rotated=last_rotated,
                    rotation_interval_days=self._interval_days,
                )
            )
        return result

    def check_overdue(self) -> list[SecretMetadata]:
        """Return only secrets that are overdue for rotation."""
        overdue: list[SecretMetadata] = []
        for meta in self.list_secrets():
            status = self.get_rotation_status(meta.secret_id)
            if status.is_overdue:
                overdue.append(meta)
        return overdue
