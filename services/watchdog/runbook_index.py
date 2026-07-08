"""Runbook-as-code index — maps RootCause codes to operator runbook entries.

Enriches every escalation payload with runbook_path, quick_fix, and manual_only flag.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.watchdog.root_cause_classifier import RootCause


@dataclass(frozen=True)
class RunbookEntry:
    """Operator runbook reference for a specific root cause."""

    path: str
    quick_fix: str
    manual_only: bool = False


RUNBOOK_INDEX: dict[RootCause, RunbookEntry] = {
    RootCause.AUTH_FAILURE: RunbookEntry(
        path="docs/runbooks/watchdog/auth-failure.md",
        quick_fix="Rotate credentials in .env and restart the affected container.",
        manual_only=True,
    ),
    RootCause.CRASH_LOOP: RunbookEntry(
        path="docs/runbooks/watchdog/crash-loop.md",
        quick_fix="Inspect logs with 'docker logs <name> --tail 100'; check OOM or config errors.",
        manual_only=False,
    ),
    RootCause.EXITED_ZERO: RunbookEntry(
        path="docs/runbooks/watchdog/exited-clean.md",
        quick_fix="Container exited cleanly; verify restart policy or intended lifecycle.",
        manual_only=False,
    ),
    RootCause.OOM_KILLED: RunbookEntry(
        path="docs/runbooks/watchdog/oom-killed.md",
        quick_fix="Increase memory limit in docker-compose.yml or investigate memory leak.",
        manual_only=True,
    ),
    RootCause.PORT_BIND_FAILURE: RunbookEntry(
        path="docs/runbooks/watchdog/port-bind-failure.md",
        quick_fix="Run 'ss -tlnp | grep <port>' to find the conflicting process and stop it.",
        manual_only=False,
    ),
    RootCause.HEALTHCHECK_MISCONFIG: RunbookEntry(
        path="docs/runbooks/watchdog/healthcheck-misconfig.md",
        quick_fix="Review HEALTHCHECK directive in Dockerfile; verify endpoint and interval.",
        manual_only=True,
    ),
    RootCause.NODE_OFFLINE: RunbookEntry(
        path="docs/runbooks/watchdog/node-offline.md",
        quick_fix="Ping the node, check VPN/firewall rules, verify Docker daemon is running.",
        manual_only=True,
    ),
    RootCause.UNKNOWN: RunbookEntry(
        path="docs/runbooks/watchdog/unknown-failure.md",
        quick_fix="Collect full logs with 'docker logs <name> --tail 200'; escalate to on-call.",
        manual_only=True,
    ),
}


def get_runbook(reason: RootCause, service_name: str | None = None) -> RunbookEntry | None:  # noqa: ARG001
    """Return the runbook entry for a given root cause, or None if not found.

    Args:
        reason: the classified root cause
        service_name: reserved for future service-specific runbook overrides

    Returns:
        RunbookEntry or None.
    """
    return RUNBOOK_INDEX.get(reason)
