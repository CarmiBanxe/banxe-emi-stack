#!/usr/bin/env python3
"""scripts/emit-ci-smoke-failure.py — ADR-035 Step 5

Emits a CI_SMOKE_FAILURE AuditEvent when the nightly smoke-gate-full
workflow fails. Called via `if: failure()` in smoke-gate-full.yml.

Write path: AuditTrail → ClickHouse (direct, if CLICKHOUSE_HOST is set).
Fallback:   BufferedAuditPort → SQLite ring-buffer (ADR-027 Option b).

Always exits 0 — never block or re-fail CI on audit emission error.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("banxe.ci-smoke-failure")

# Repo root on sys.path so src.safeguarding imports work from scripts/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.safeguarding.audit_trail import AuditEvent, AuditTrail  # noqa: E402


def build_event() -> AuditEvent:
    run_id = os.getenv("GITHUB_RUN_ID", "unknown")
    repo = os.getenv("GITHUB_REPOSITORY", "CarmiBanxe/banxe-emi-stack")
    return AuditEvent(
        event_type="CI_SMOKE_FAILURE",
        entity_id=f"ci-smoke-{run_id}",
        actor="smoke-gate-full / GitHub Actions",
        payload={
            "workflow": "smoke-gate-full.yml",
            "run_id": run_id,
            "run_url": f"https://github.com/{repo}/actions/runs/{run_id}",
            "tier": "full",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
        severity="CRITICAL",
    )


def emit() -> None:
    event = build_event()

    clickhouse_host = os.getenv("CLICKHOUSE_HOST", "")
    if clickhouse_host:
        ch_url = f"http://{clickhouse_host}:8123"
        trail = AuditTrail(
            clickhouse_url=ch_url,
            database=os.getenv("CLICKHOUSE_DB", "banxe"),
            dry_run=False,
        )
        if trail.log(event):
            logger.info(
                "CI_SMOKE_FAILURE → ClickHouse: event_id=%s run_id=%s",
                event.event_id,
                os.getenv("GITHUB_RUN_ID", "unknown"),
            )
            return
        logger.warning("ClickHouse write failed — falling back to BufferedAuditPort")

    from src.safeguarding.buffered_audit_port import BufferedAuditPort

    buffer_path = os.getenv("AUDIT_BUFFER_PATH", "/tmp/banxe-audit-buffer.db")  # noqa: S108  # nosec B108
    port = BufferedAuditPort(db_path=buffer_path)
    port.record(event)
    logger.info(
        "CI_SMOKE_FAILURE → SQLite buffer: entity_id=%s path=%s",
        event.entity_id,
        buffer_path,
    )


def main() -> None:
    try:
        emit()
    except Exception as exc:  # noqa: BLE001
        logger.error("CI_SMOKE_FAILURE emission error (non-fatal): %s", exc)
    sys.exit(0)


if __name__ == "__main__":
    main()
