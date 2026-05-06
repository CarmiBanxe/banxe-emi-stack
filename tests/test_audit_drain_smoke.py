"""Smoke tests for ADR-027 step 3: drain script + end-to-end buffer flow.

T1 — E2E: record 3 events → drain to mock AuditTrail → all 3 drained, pending=0
T2 — Drain script subprocess: exits 0 with AUDIT_DRY_RUN=true
T3 — Drain with target returning False → events stay in buffer
"""
from __future__ import annotations

import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from services.recon.recon_models import ReconAuditEntry, ReconStatus
from src.safeguarding.buffered_audit_port import BufferedAuditPort


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_entry(recon_id: str = "smoke-recon") -> ReconAuditEntry:
    return ReconAuditEntry(
        recon_id=recon_id,
        action="DAILY_RECON",
        status=ReconStatus.BALANCED,
        client_funds_total=Decimal("2500.00"),
        safeguarding_total=Decimal("2500.00"),
        actor="SMOKE_TEST",
    )


class _AlwaysTrue:
    """Mock AuditTrail that always succeeds."""

    def __init__(self) -> None:
        self.calls: int = 0

    def log(self, event: Any) -> bool:
        self.calls += 1
        return True


class _AlwaysFalse:
    """Mock AuditTrail that always fails (simulates CH down)."""

    def log(self, event: Any) -> bool:
        return False


# ---------------------------------------------------------------------------
# T1 — End-to-end: record 3 → drain all → pending=0
# ---------------------------------------------------------------------------


def test_e2e_record_drain_all(tmp_path: Path) -> None:
    """record 3 events, drain to mock target → all 3 forwarded, pending=0."""
    port = BufferedAuditPort(db_path=tmp_path / "buf.db")
    for i in range(3):
        port.record(make_entry(recon_id=f"smoke-{i}"))

    assert port.pending_count() == 3

    target = _AlwaysTrue()
    drained = port.drain(target=target, batch_size=100)

    assert drained == 3
    assert target.calls == 3
    assert port.pending_count() == 0


# ---------------------------------------------------------------------------
# T2 — Drain script subprocess exits 0
# ---------------------------------------------------------------------------


def test_drain_script_exits_zero(tmp_path: Path) -> None:
    """scripts/audit-buffer-drain.py exits 0 with AUDIT_DRY_RUN=true."""
    repo_root = Path(__file__).parent.parent
    script = repo_root / "scripts" / "audit-buffer-drain.py"

    env = {
        **os.environ,
        "AUDIT_DRY_RUN": "true",
        "AUDIT_BUFFER_PATH": str(tmp_path / "drain-smoke.db"),
        "PYTHONPATH": str(repo_root),
    }

    result = subprocess.run(
        [sys.executable, str(script)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"Script failed:\nstdout={result.stdout}\nstderr={result.stderr}"


# ---------------------------------------------------------------------------
# T3 — CH down (target returns False) → events stay in buffer
# ---------------------------------------------------------------------------


def test_drain_ch_down_keeps_events(tmp_path: Path) -> None:
    """When target.log() returns False, events are NOT marked drained."""
    port = BufferedAuditPort(db_path=tmp_path / "buf.db")
    for i in range(3):
        port.record(make_entry(recon_id=f"stuck-{i}"))

    drained = port.drain(target=_AlwaysFalse(), batch_size=100)

    assert drained == 0
    assert port.pending_count() == 3
