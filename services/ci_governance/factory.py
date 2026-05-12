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
import time

from services.ci_governance.drift_alert_emitter import DriftAlertEmitter
from services.ci_governance.drift_detector import DriftDetector
from services.ci_governance.in_memory_protection_reader import (
    InMemoryProtectionReader,
)

_DEFAULT_BASELINE_PATH = ".github/protection-update-v2.json"


@lru_cache(maxsize=1)
def get_protection_reader() -> InMemoryProtectionReader:
    """Default singleton — an empty InMemoryProtectionReader. The CLI
    overrides this with a payload-supplied reader at runtime; tests
    construct readers directly with their fixture data."""
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
