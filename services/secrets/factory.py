"""Secret rotation DI factory (ADR-032, G-SEC-01).

Reads configuration from environment and returns a configured
EnvSecretRotator. Feature flag SECRET_ROTATION_ENABLED controls activation.

Usage:
    from services.secrets.factory import get_secret_rotator
    rotator = get_secret_rotator()  # raises SecretRotationDisabledError if disabled
"""

from __future__ import annotations

from dataclasses import dataclass
import os

from services.secrets.env_secret_rotator import EnvSecretRotator


class SecretRotationDisabledError(Exception):
    """Raised when rotation operations are attempted while disabled."""


@dataclass(frozen=True)
class SecretRotationConfig:
    """Configuration for EnvSecretRotator, loaded from environment."""

    enabled: bool
    interval_days: int
    managed_keys: list[str]
    env_file_path: str

    @classmethod
    def from_env(cls) -> SecretRotationConfig:
        """Load secret rotation config from environment variables."""
        keys_raw = os.environ.get("SECRET_ROTATION_MANAGED_KEYS", "")
        managed_keys = [k.strip() for k in keys_raw.split(",") if k.strip()]

        return cls(
            enabled=os.environ.get("SECRET_ROTATION_ENABLED", "false").lower() == "true",
            interval_days=int(os.environ.get("SECRET_ROTATION_INTERVAL_DAYS", "90")),
            managed_keys=managed_keys,
            env_file_path=os.environ.get("SECRET_ROTATION_ENV_FILE", ".env"),
        )


def get_secret_rotator(config: SecretRotationConfig | None = None) -> EnvSecretRotator:
    """Create a configured EnvSecretRotator from environment.

    Raises:
        SecretRotationDisabledError: if SECRET_ROTATION_ENABLED != 'true'.
    """
    cfg = config or SecretRotationConfig.from_env()

    if not cfg.enabled:
        raise SecretRotationDisabledError(
            "Secret rotation disabled (SECRET_ROTATION_ENABLED != 'true'). "
            "Set SECRET_ROTATION_ENABLED=true to enable."
        )

    return EnvSecretRotator(
        rotation_interval_days=cfg.interval_days,
        env_file_path=cfg.env_file_path,
        managed_keys=cfg.managed_keys,
    )
