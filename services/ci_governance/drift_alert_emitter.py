"""
drift_alert_emitter.py — Route DriftResult into the ADR-033 alert pipeline
(S16.6 CI governance drift sentry).

Pure delegator: builds an `Alert` and calls the injected
`AlertRoutingPort.send_alert`. The Port is async; the emitter is sync;
the bridge uses `loop.create_task` when a running loop is detected and
`asyncio.run` otherwise. No contextlib.suppress here — caller decides
defence-in-depth (the CLI script wraps the call in suppress for cron-safe
operation).

Severity mapping:
  - `result.strict_weakened` → CRITICAL (protection actively weakened)
  - any other drift             → MAJOR
  - no drift                    → no alert emitted (early return)

Event-type constant:
  EVENT_CI_PROTECTION_DRIFT = "CI_PROTECTION_DRIFT"
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import time
from typing import TYPE_CHECKING

from services.alerting.alert_port import Alert, AlertCategory, AlertSeverity

if TYPE_CHECKING:
    from services.alerting.alert_port import AlertRoutingPort
    from services.ci_governance.drift_detector import DriftResult


EVENT_CI_PROTECTION_DRIFT = "CI_PROTECTION_DRIFT"
_DEFAULT_SOURCE = "ci-governance-drift-sentry"


class DriftAlertEmitter:
    """Build and route a DriftResult into the ADR-033 alert pipeline."""

    def __init__(
        self,
        alert_router: AlertRoutingPort,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._alert_router = alert_router
        self._clock = clock

    def emit(self, result: DriftResult) -> None:
        if not result.drift_detected:
            return  # nothing to alert on

        severity = AlertSeverity.CRITICAL if result.strict_weakened else AlertSeverity.WARNING
        # Repo AlertSeverity enum is {INFO, WARNING, CRITICAL}; map "MAJOR" intent
        # onto WARNING here. CRITICAL reserved for the strict-weakened class.

        body = (
            f"{EVENT_CI_PROTECTION_DRIFT}\n"
            f"baseline={result.baseline_path}\n"
            f"checked_at={result.checked_at}\n"
            f"summary={result.summary}\n"
            f"missing_contexts={result.missing_contexts}\n"
            f"extra_contexts={result.extra_contexts}\n"
            f"strict_differs={result.strict_differs}\n"
            f"strict_weakened={result.strict_weakened}\n"
            f"enforce_admins_differs={result.enforce_admins_differs}\n"
        )
        alert = Alert(
            category=AlertCategory.GENERIC,
            severity=severity,
            title=f"{EVENT_CI_PROTECTION_DRIFT} on main",
            body=body,
            source=_DEFAULT_SOURCE,
            metadata={
                "event_type": EVENT_CI_PROTECTION_DRIFT,
                "baseline_path": result.baseline_path,
                "missing_contexts": list(result.missing_contexts),
                "extra_contexts": list(result.extra_contexts),
                "strict_differs": result.strict_differs,
                "strict_weakened": result.strict_weakened,
                "enforce_admins_differs": result.enforce_admins_differs,
            },
            owner="CTIO",
        )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop — one-shot sync invocation.
            asyncio.run(self._alert_router.send_alert(alert))
            return
        loop.create_task(self._alert_router.send_alert(alert))
