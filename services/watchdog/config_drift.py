"""GAP-C — runtime config-drift detection for watchdog.

Reuses DriftResult + DriftHistoryStore from services.ci_governance without
duplication.  I-27: drift → ESCALATE only; auto-fix deferred to GAP-A.

Two incident classes:
  1. Docker secret drift (e.g. POSTGRES_PASSWORD hash mismatch volume vs compose).
  2. Ollama override.conf drift (e.g. OLLAMA_NUM_CTX=131072 ≠ baseline 8192).

Sensitive values: SHA-256 hash comparison only — raw values NEVER stored or logged.
"""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import logging
from pathlib import Path
import time
from typing import Protocol

import yaml

from services.ci_governance.drift_detector import DriftResult

log = logging.getLogger(__name__)

EVENT_CONFIG_DRIFT = "RUNTIME_CONFIG_DRIFT"

_SENSITIVE_PATTERNS: tuple[str, ...] = (
    "password",
    "secret",
    "token",
    "key",
    "passwd",
    "pwd",
    "credentials",
)


def _is_sensitive_key(key: str) -> bool:
    low = key.lower()
    return any(p in low for p in _SENSITIVE_PATTERNS)


def _hash_value(value: str) -> str:
    """One-way SHA-256 fingerprint — 16-hex prefix; raw value is never returned."""
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()[:16]


class RuntimeConfigReaderPort(Protocol):
    """Port for reading live runtime config state.

    Returns {key → value} where sensitive values are pre-hashed by the reader.
    Duck-type compatible with DriftDetector's reader concept.
    """

    def read_live_config(self) -> dict[str, str]: ...


class InMemoryRuntimeConfigReader:
    """Test stub — returns a fixed config dict verbatim."""

    def __init__(self, config: dict[str, str]) -> None:
        self._config = dict(config)

    def read_live_config(self) -> dict[str, str]:
        return dict(self._config)


class CompositeRuntimeConfigReader:
    """Merge results from multiple readers; later readers overwrite earlier ones."""

    def __init__(self, readers: list[RuntimeConfigReaderPort]) -> None:
        self._readers = readers

    def read_live_config(self) -> dict[str, str]:
        merged: dict[str, str] = {}
        for r in self._readers:
            merged.update(r.read_live_config())
        return merged


class DockerEnvConfigReader:
    """Read env vars from running Docker containers.

    Sensitive keys are SHA-256 hashed before returning (raw secrets never leave).
    """

    def __init__(
        self,
        container_names: list[str],
        docker_socket: str = "/var/run/docker.sock",
    ) -> None:
        self._containers = container_names
        self._socket = docker_socket

    def read_live_config(self) -> dict[str, str]:
        try:
            import docker  # optional dep; guarded

            client = docker.DockerClient(base_url=f"unix://{self._socket}")
        except Exception as exc:
            log.warning("docker client unavailable: %s", exc)
            return {}

        result: dict[str, str] = {}
        for name in self._containers:
            try:
                container = client.containers.get(name)
                env_list: list[str] = (container.attrs.get("Config") or {}).get("Env") or []
                for entry in env_list:
                    if "=" not in entry:
                        continue
                    k, _, v = entry.partition("=")
                    full_key = f"{name}.{k}"
                    result[full_key] = _hash_value(v) if _is_sensitive_key(k) else v
            except Exception as exc:
                log.warning("cannot inspect container %s: %s", name, exc)

        return result


class FileBasedOllamaConfigReader:
    """Read key=value lines from Ollama override.conf files.

    Node names are used as key prefixes so the caller can distinguish
    which node each setting belongs to.
    """

    def __init__(self, node_conf_paths: dict[str, Path]) -> None:
        self._paths = node_conf_paths  # {node_name: path_to_override.conf}

    def read_live_config(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for node, path in self._paths.items():
            if not path.is_file():
                continue
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip()
                full_key = f"{node}.{k}"
                result[full_key] = _hash_value(v) if _is_sensitive_key(k) else v
        return result


class ConfigDriftDetector:
    """Detect runtime config drift vs a git-tracked YAML baseline.

    Returns DriftResult from services.ci_governance — reuses DriftHistoryStore
    and DriftAlertEmitter unchanged.

    Field mapping:
      missing_contexts ← baseline keys absent in live + value-mismatched keys
      extra_contexts   ← live keys absent in baseline
      strict_differs   ← any value mismatch
      strict_weakened  ← sensitive key hash mismatch → CRITICAL alert
    """

    def __init__(
        self,
        reader: RuntimeConfigReaderPort,
        baseline_path: str | Path,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._reader = reader
        self._baseline_path = Path(baseline_path)
        self._clock = clock

    def detect(self) -> DriftResult:
        if not self._baseline_path.is_file():
            raise FileNotFoundError(f"config baseline not found: {self._baseline_path}")

        raw = yaml.safe_load(self._baseline_path.read_text(encoding="utf-8"))
        baseline: dict[str, str] = {k: str(v) for k, v in (raw.get("config") or {}).items()}
        live = self._reader.read_live_config()

        baseline_keys = set(baseline)
        live_keys = set(live)
        missing = sorted(baseline_keys - live_keys)
        extra = sorted(live_keys - baseline_keys)

        mismatch_plain: list[str] = []
        mismatch_sensitive: list[str] = []
        for key in sorted(baseline_keys & live_keys):
            b_val = baseline[key]
            l_val = live[key]
            if b_val == l_val:
                continue
            # Either side is a hash → treat as sensitive mismatch
            if l_val.startswith("sha256:") or b_val.startswith("sha256:"):
                mismatch_sensitive.append(key)
            else:
                mismatch_plain.append(key)

        drift_detected = bool(missing or extra or mismatch_plain or mismatch_sensitive)
        strict_differs = bool(mismatch_plain or mismatch_sensitive)
        strict_weakened = bool(mismatch_sensitive)

        parts: list[str] = []
        if missing:
            parts.append(f"missing_keys={missing}")
        if extra:
            parts.append(f"extra_keys={extra}")
        if mismatch_plain:
            parts.append(f"value_mismatch={mismatch_plain}")
        if mismatch_sensitive:
            # Key names only — never raw values or hashes in summary
            parts.append(f"secret_hash_mismatch={mismatch_sensitive}")
        summary = "; ".join(parts) if parts else "no drift"

        return DriftResult(
            drift_detected=drift_detected,
            missing_contexts=missing + mismatch_plain + mismatch_sensitive,
            extra_contexts=extra,
            strict_differs=strict_differs,
            strict_weakened=strict_weakened,
            enforce_admins_differs=False,
            baseline_path=str(self._baseline_path),
            checked_at=self._clock(),
            summary=summary,
        )
