#!/usr/bin/env python3
"""ADR-033 Step 3: operational smoke check for alert routing.

Health-checks the configured AlertRoutingPort and sends one benign test
Alert. Exits 0 on success, 1 on failure. Safe to run from cron / CI.
When ALERT_ENABLED=false (default) the in-memory adapter is exercised
instead of the live n8n+Telegram pipe.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.alerting.alert_port import (  # noqa: E402
    Alert,
    AlertCategory,
    AlertSeverity,
)
from services.alerting.di import get_alert_adapter  # noqa: E402


async def _run() -> int:
    adapter = get_alert_adapter()
    try:
        healthy = await adapter.health_check()
        print(f"health_check: {healthy}")

        alert = Alert(
            category=AlertCategory.GENERIC,
            severity=AlertSeverity.INFO,
            title="Alert routing smoke test",
            body="Operational check from alert-routing-check.py",
        )
        delivered = await adapter.send_alert(alert)
    finally:
        close = getattr(adapter, "close", None)
        if callable(close):
            await close()

    if delivered:
        print("PASS: alert delivered")
        return 0
    print("FAIL: delivery failed")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
