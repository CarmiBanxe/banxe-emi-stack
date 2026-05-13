"""
factory.py — DI singletons for the CI governance drift sentry (S16.6).

Default-config singletons:
  get_protection_reader()    — InMemoryProtectionReader({}) by default.
                              CLI overrides by constructing the reader
                              directly with a payload dict; tests do the
                              same.
  get_drift_detector()       — DriftDetector wired to the default reader
                              and the S16.5 baseline at
                              `.github/protection-update-v2.json`.
  get_drift_alert_emitter()  — DriftAlertEmitter wired to the shared
                              ADR-033 alert sink via
                              services.alerting.di.get_alert_adapter().

Naming deviation (noted in commit body): the S16.6 brief calls the
emitter dependency `alert_router`; the actual repo DI function is
`services.alerting.di.get_alert_adapter` (verified by reading
api/deps.py:297 and services/alerting/di.py at this branch's base
commit). The Port itself is `AlertRoutingPort`; the variable naming
inside DriftAlertEmitter preserves the brief's wording for the
constructor parameter, while the factory uses the real function name.
"""

from __future__ import annotations

from functools import lru_cache
import os
import time

from services.ci_governance.drift_alert_emitter import DriftAlertEmitter
from services.ci_governance.drift_detector import DriftDetector
from services.ci_governance.gh_api_protection_reader import (
    GitHubApiProtectionReader,
)
from services.ci_governance.in_memory_protection_reader import (
    InMemoryProtectionReader,
)
from services.ci_governance.protection_reader_port import (
    GitHubProtectionReaderPort,
)

_DEFAULT_BASELINE_PATH = ".github/protection-update-v2.json"
_TOKEN_ENV_PRIORITY: tuple[str, ...] = (
    "CI_GOVERNANCE_GH_TOKEN",
    "GH_TOKEN",
    "GITHUB_TOKEN",
)


def resolve_gh_token() -> str | None:
    """Token resolution order: CI_GOVERNANCE_GH_TOKEN → GH_TOKEN → GITHUB_TOKEN.

    Returns the first non-empty value, or None if none are set. Public so
    tests can exercise the priority order directly.
    """
    for key in _TOKEN_ENV_PRIORITY:
        val = os.environ.get(key)
        if val:
            return val
    return None


@lru_cache(maxsize=1)
def get_real_gh_protection_reader() -> GitHubApiProtectionReader:
    """Singleton real-API reader, wired from CI_GOVERNANCE_* env.

    The token itself is NOT cached on the adapter — token_provider is
    `resolve_gh_token` so rotated tokens are picked up at read time.
    """
    return GitHubApiProtectionReader(
        owner=os.environ.get("CI_GOVERNANCE_REPO_OWNER", "CarmiBanxe"),
        repo=os.environ.get("CI_GOVERNANCE_REPO_NAME", "banxe-emi-stack"),
        branch=os.environ.get("CI_GOVERNANCE_BRANCH", "main"),
        token_provider=resolve_gh_token,
    )


@lru_cache(maxsize=1)
def get_protection_reader() -> GitHubProtectionReaderPort:
    """Env-driven reader selection (S16.7 extension of S16.6 default).

    CI_GOVERNANCE_READER_MODE ∈ {"in_memory", "gh_api", "auto"}:
      - "in_memory" (or absent) → InMemoryProtectionReader({}) — S16.6 default
      - "gh_api"                → GitHubApiProtectionReader (real, read-only)
      - "auto"                  → gh_api if any CI_GOVERNANCE_* / GH_TOKEN /
                                  GITHUB_TOKEN env present, else in_memory
    """
    mode = os.environ.get("CI_GOVERNANCE_READER_MODE", "in_memory").strip().lower()
    if mode == "gh_api":
        return get_real_gh_protection_reader()
    if mode == "auto":
        if resolve_gh_token() is not None:
            return get_real_gh_protection_reader()
        return InMemoryProtectionReader({})
    # "in_memory" and any unrecognised value fall back to S16.6 default
    return InMemoryProtectionReader({})


@lru_cache(maxsize=1)
def get_drift_detector() -> DriftDetector:
    return DriftDetector(
        reader=get_protection_reader(),
        baseline_path=_DEFAULT_BASELINE_PATH,
        clock=time.time,
    )


@lru_cache(maxsize=1)
def get_drift_alert_emitter() -> DriftAlertEmitter:
    """Singleton DriftAlertEmitter bound to the shared ADR-033 alert sink.

    Lazy-imports services.alerting.di.get_alert_adapter so callers that
    never need alerting don't pay the alert-DI import cost.
    """
    from services.alerting.di import get_alert_adapter

    return DriftAlertEmitter(alert_router=get_alert_adapter(), clock=time.time)


@lru_cache(maxsize=1)
def get_drift_history_store():
    """Singleton DriftHistoryStore; path from CI_GOVERNANCE_DRIFT_HISTORY_PATH env."""
    from services.ci_governance.drift_history_store import DriftHistoryStore

    history_path = os.environ.get(
        "CI_GOVERNANCE_DRIFT_HISTORY_PATH",
        "/var/cache/banxe/drift-history.jsonl",
    )
    return DriftHistoryStore(history_path=history_path, clock=time.time)


@lru_cache(maxsize=1)
def get_drift_metrics_exporter():
    """Singleton DriftMetricsExporter wired to the shared history store (S16.11)."""
    from services.ci_governance.drift_metrics_exporter import DriftMetricsExporter

    return DriftMetricsExporter(
        history_store=get_drift_history_store(),
        clock=time.time,
    )


@lru_cache(maxsize=1)
def get_snapshot_writer():
    """Singleton ProtectionSnapshotWriter wired to the configured reader.

    Reuses the env-driven get_protection_reader() so the snapshot host
    can be in_memory / gh_api / auto mode independently of the drift-
    sentry host that consumes the snapshot file (S16.6 + S16.7 paths).
    """
    from services.ci_governance.snapshot_writer import ProtectionSnapshotWriter

    return ProtectionSnapshotWriter(reader=get_protection_reader(), clock=time.time)
