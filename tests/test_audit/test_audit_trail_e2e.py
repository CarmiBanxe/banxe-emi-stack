"""G-CASS-02: E2E audit-trail coverage for BufferedAuditPort.

5 tests covering ADR-027 / FCA CASS 15 §15.10 / DORA Art.14(2) durability:
  1. buffer survives backend failure (ClickHouse 5xx)
  2. buffer drains on backend recovery
  3. failure path is observable (no silent loss — closes G-CASS-01)
  4. recon cycle produces a complete audit record
  5. I-24 append-only invariant — no public update / delete / modify methods
"""

from __future__ import annotations

from decimal import Decimal
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any
from unittest.mock import patch

import pytest
from src.safeguarding.buffered_audit_port import BufferedAuditPort

from services.recon.recon_models import ReconAuditEntry, ReconStatus


def _make_entry(recon_id: str = "recon-e2e") -> ReconAuditEntry:
    return ReconAuditEntry(
        recon_id=recon_id,
        action="DAILY_RECON",
        status=ReconStatus.BALANCED,
        client_funds_total=Decimal("1000.00"),
        safeguarding_total=Decimal("1000.00"),
        actor="SYSTEM",
    )


class _MockTarget:
    """Drain target double — switchable between failure (5xx) and success."""

    def __init__(self, succeed: bool = True) -> None:
        self.succeed = succeed
        self.logged: list[Any] = []

    def log(self, event: Any) -> bool:
        self.logged.append(event)
        return self.succeed


def test_buffered_audit_survives_backend_failure(tmp_path: Path) -> None:
    port = BufferedAuditPort(db_path=tmp_path / "buf.db")
    for i in range(3):
        port.record(_make_entry(recon_id=f"recon-{i}"))

    failing_target = _MockTarget(succeed=False)
    drained = port.drain(failing_target)

    assert drained == 0
    assert port.pending_count() == 3


def test_buffered_audit_drains_on_backend_recovery(tmp_path: Path) -> None:
    port = BufferedAuditPort(db_path=tmp_path / "buf.db")
    for i in range(3):
        port.record(_make_entry(recon_id=f"recon-{i}"))

    failing_target = _MockTarget(succeed=False)
    assert port.drain(failing_target) == 0
    assert port.pending_count() == 3

    recovered_target = _MockTarget(succeed=True)
    drained = port.drain(recovered_target)

    assert drained == 3
    assert port.pending_count() == 0
    assert len(recovered_target.logged) == 3


def test_audit_event_never_silently_lost(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    port = BufferedAuditPort(db_path=tmp_path / "buf.db")

    with (
        caplog.at_level(logging.ERROR, logger="src.safeguarding.buffered_audit_port"),
        patch("sqlite3.connect", side_effect=sqlite3.OperationalError("disk full")),
    ):
        port.record(_make_entry())

    assert any(
        "BufferedAuditPort.record() failed" in record.message and record.levelno >= logging.ERROR
        for record in caplog.records
    ), "G-CASS-01: dual-failure path must surface an error log, not silently drop the event"


def test_recon_cycle_produces_audit_record(tmp_path: Path) -> None:
    db = tmp_path / "buf.db"
    port = BufferedAuditPort(db_path=db)

    entry = _make_entry(recon_id="recon-cycle-001")
    port.record(entry)

    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT event_json, created_at FROM audit_buffer WHERE drained=0"
        ).fetchone()
    finally:
        conn.close()

    assert row is not None, "recon cycle must produce a buffered audit record"
    event_json, created_at = row
    payload = json.loads(event_json)

    assert payload["recon_id"] == "recon-cycle-001"
    assert payload["action"] == "DAILY_RECON"
    assert payload["status"] == ReconStatus.BALANCED.value
    assert payload["timestamp"]
    assert created_at


def test_audit_append_only_no_update_no_delete(tmp_path: Path) -> None:
    port = BufferedAuditPort(db_path=tmp_path / "buf.db")

    for forbidden in (
        "update",
        "update_entry",
        "modify",
        "edit",
        "delete",
        "delete_entry",
        "remove",
    ):
        assert not hasattr(port, forbidden), (
            f"I-24 violation: BufferedAuditPort exposes '{forbidden}' — audit entries must be append-only"
        )

    assert hasattr(port, "record")
    assert hasattr(port, "drain")
