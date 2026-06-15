"""Unit tests for DriftAlertEmitter (S16.6).

Repo runs pytest-asyncio in asyncio_mode = "auto"; async test functions
execute under the asyncio runner. The emitter detects a running loop and
schedules `send_alert` via `loop.create_task` — we await a few yields so
the scheduled task lands in the FakeAlertRouter's captured list.
"""

from __future__ import annotations

import asyncio

from services.alerting.alert_port import Alert, AlertRoutingPort, AlertSeverity
from services.ci_governance.drift_alert_emitter import (
    EVENT_CI_PROTECTION_DRIFT,
    DriftAlertEmitter,
)
from services.ci_governance.drift_detector import DriftResult


class FakeAlertRouter(AlertRoutingPort):
    def __init__(self) -> None:
        self.alerts: list[Alert] = []

    async def send_alert(self, alert: Alert) -> bool:
        self.alerts.append(alert)
        return True

    async def health_check(self) -> bool:
        return True


async def _drain_loop(n: int = 5) -> None:
    for _ in range(n):
        await asyncio.sleep(0)


def _drift_result(
    *,
    drift: bool = True,
    strict_weakened: bool = False,
    missing: list[str] | None = None,
    extra: list[str] | None = None,
    strict_differs: bool = False,
    admins_differs: bool = False,
) -> DriftResult:
    return DriftResult(
        drift_detected=drift,
        missing_contexts=missing or [],
        extra_contexts=extra or [],
        strict_differs=strict_differs,
        strict_weakened=strict_weakened,
        enforce_admins_differs=admins_differs,
        baseline_path=".github/protection-update-v2.json",
        checked_at=1714000000.0,
        summary="test-fixture",
    )


async def test_emit_routes_drift_alert_to_alert_router() -> None:
    router = FakeAlertRouter()
    emitter = DriftAlertEmitter(alert_router=router, clock=lambda: 1714000000.0)
    emitter.emit(_drift_result(missing=["Pytest (coverage >= 80%)"]))
    await _drain_loop()
    assert len(router.alerts) == 1
    alert = router.alerts[0]
    assert alert.title.startswith(EVENT_CI_PROTECTION_DRIFT)
    assert EVENT_CI_PROTECTION_DRIFT in alert.body


async def test_emit_uses_major_severity_for_context_drift() -> None:
    router = FakeAlertRouter()
    emitter = DriftAlertEmitter(alert_router=router, clock=lambda: 1714000000.0)
    emitter.emit(_drift_result(missing=["Pytest (coverage >= 80%)"]))
    await _drain_loop()
    # Repo AlertSeverity vocabulary lacks "MAJOR"; we map context-drift to
    # WARNING (severity below CRITICAL). CRITICAL is reserved for the
    # strict-weakened class. Documented in drift_alert_emitter.py.
    assert router.alerts[0].severity == AlertSeverity.WARNING


async def test_emit_uses_critical_severity_when_strict_changed_to_false() -> None:
    router = FakeAlertRouter()
    emitter = DriftAlertEmitter(alert_router=router, clock=lambda: 1714000000.0)
    emitter.emit(_drift_result(strict_differs=True, strict_weakened=True))
    await _drain_loop()
    assert router.alerts[0].severity == AlertSeverity.CRITICAL


async def test_emit_does_not_emit_when_no_drift_detected() -> None:
    router = FakeAlertRouter()
    emitter = DriftAlertEmitter(alert_router=router, clock=lambda: 1714000000.0)
    emitter.emit(_drift_result(drift=False))
    await _drain_loop()
    assert router.alerts == []


async def test_emit_includes_canonical_event_type_CI_PROTECTION_DRIFT() -> None:
    router = FakeAlertRouter()
    emitter = DriftAlertEmitter(alert_router=router, clock=lambda: 1714000000.0)
    emitter.emit(_drift_result(missing=["x"]))
    await _drain_loop()
    alert = router.alerts[0]
    assert alert.metadata["event_type"] == EVENT_CI_PROTECTION_DRIFT
    assert EVENT_CI_PROTECTION_DRIFT == "CI_PROTECTION_DRIFT"
