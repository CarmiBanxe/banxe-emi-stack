"""Sprint 3+ Watchdog Prometheus Exporter — lightweight metrics for watchdog decisions.

Exposes counters/gauges in Prometheus text exposition format (0.0.4).
No external dependencies — plain asyncio HTTP server on /metrics.
"""

from __future__ import annotations

import asyncio
import logging
import time

log = logging.getLogger(__name__)


class WatchdogMetrics:
    """In-memory counters/gauges for watchdog decisions.

    Metrics exposed:
    - watchdog_decisions_total{action}  counter   all decisions made, by action
    - watchdog_repairs_total{status}    counter   ok/fail outcomes
    - watchdog_escalations_total        counter   escalations to human operator
    - watchdog_targets_unhealthy        gauge     current unhealthy targets count
    - watchdog_last_success_timestamp   gauge     unix ts of last repair_ok
    """

    def __init__(self) -> None:
        self._decisions: dict[str, int] = {}
        self._repairs_ok: int = 0
        self._repairs_fail: int = 0
        self._escalations: int = 0
        self._targets_unhealthy: int = 0
        self._last_success_ts: float = 0.0

    def record_decision(self, action: str) -> None:
        """Increment watchdog_decisions_total for the given action."""
        self._decisions[action] = self._decisions.get(action, 0) + 1

    def record_repair_ok(self) -> None:
        """Increment watchdog_repairs_total{status=ok} and stamp last_success."""
        self._repairs_ok += 1
        self._last_success_ts = time.time()

    def record_repair_fail(self) -> None:
        """Increment watchdog_repairs_total{status=fail}."""
        self._repairs_fail += 1

    def record_escalation(self) -> None:
        """Increment watchdog_escalations_total."""
        self._escalations += 1

    def set_unhealthy_targets(self, count: int) -> None:
        """Set watchdog_targets_unhealthy gauge."""
        self._targets_unhealthy = count

    def render(self) -> str:
        """Return all metrics in Prometheus text exposition format."""
        lines: list[str] = []

        lines += [
            "# HELP watchdog_decisions_total Total repair decisions made, by action",
            "# TYPE watchdog_decisions_total counter",
        ]
        for action, count in sorted(self._decisions.items()):
            lines.append(f'watchdog_decisions_total{{action="{action}"}} {count}')
        if not self._decisions:
            lines.append('watchdog_decisions_total{action="none"} 0')

        lines += [
            "# HELP watchdog_repairs_total Total repair attempts by outcome",
            "# TYPE watchdog_repairs_total counter",
            f'watchdog_repairs_total{{status="ok"}} {self._repairs_ok}',
            f'watchdog_repairs_total{{status="fail"}} {self._repairs_fail}',
            "# HELP watchdog_escalations_total Total escalations to human operator",
            "# TYPE watchdog_escalations_total counter",
            f"watchdog_escalations_total {self._escalations}",
            "# HELP watchdog_targets_unhealthy Current unhealthy monitored targets",
            "# TYPE watchdog_targets_unhealthy gauge",
            f"watchdog_targets_unhealthy {self._targets_unhealthy}",
            "# HELP watchdog_last_success_timestamp Unix timestamp of last successful repair",
            "# TYPE watchdog_last_success_timestamp gauge",
            f"watchdog_last_success_timestamp {self._last_success_ts}",
        ]

        return "\n".join(lines) + "\n"

    async def serve(self, port: int = 9091) -> None:
        """Serve /metrics on the given port via a minimal asyncio HTTP server."""

        async def _handle(
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
        ) -> None:
            try:
                await asyncio.wait_for(reader.read(4096), timeout=5.0)
                body = self.render().encode()
                writer.write(
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: text/plain; version=0.0.4\r\n"
                    + f"Content-Length: {len(body)}\r\n\r\n".encode()
                    + body
                )
                await writer.drain()
            except Exception:  # noqa: BLE001
                pass
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(_handle, "0.0.0.0", port)  # noqa: S104
        log.info("watchdog metrics server on :%d", port)
        async with server:
            await server.serve_forever()
