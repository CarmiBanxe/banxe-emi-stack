"""Tests for BufferedAuditPort — ADR-027 Step 1.

8 tests covering: record, drain (success/partial/raising), pending_count,
cleanup, fail-safe on sqlite error, and thread-safety.
"""
from __future__ import annotations

import sqlite3
import threading
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from services.recon.recon_models import ReconAuditEntry, ReconStatus
from src.safeguarding.buffered_audit_port import BufferedAuditPort


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_entry(recon_id: str = "recon-test") -> ReconAuditEntry:
    return ReconAuditEntry(
        recon_id=recon_id,
        action="DAILY_RECON",
        status=ReconStatus.BALANCED,
        client_funds_total=Decimal("1000.00"),
        safeguarding_total=Decimal("1000.00"),
        actor="SYSTEM",
    )


class MockTarget:
    def __init__(
        self,
        always_returns: bool = True,
        fail_on_call: int | None = None,
        raise_on_call: int | None = None,
    ) -> None:
        self._always_returns = always_returns
        self._fail_on_call = fail_on_call
        self._raise_on_call = raise_on_call
        self._call_count = 0
        self.logged_events: list[Any] = []

    def log(self, event: Any) -> bool:
        self._call_count += 1
        self.logged_events.append(event)
        if self._raise_on_call is not None and self._call_count == self._raise_on_call:
            raise RuntimeError("target exploded")
        if self._fail_on_call is not None and self._call_count == self._fail_on_call:
            return False
        return self._always_returns


# ---------------------------------------------------------------------------
# T1 — single record increases pending_count to 1
# ---------------------------------------------------------------------------


def test_record_single_increases_pending(tmp_path: Path) -> None:
    port = BufferedAuditPort(db_path=tmp_path / "buf.db")
    port.record(make_entry())
    assert port.pending_count() == 1


# ---------------------------------------------------------------------------
# T2 — five records increase pending_count to 5
# ---------------------------------------------------------------------------


def test_record_multiple_increases_pending(tmp_path: Path) -> None:
    port = BufferedAuditPort(db_path=tmp_path / "buf.db")
    for i in range(5):
        port.record(make_entry(recon_id=f"recon-{i}"))
    assert port.pending_count() == 5


# ---------------------------------------------------------------------------
# T3 — drain with always-True target drains all; pending_count → 0
# ---------------------------------------------------------------------------


def test_drain_all_success(tmp_path: Path) -> None:
    port = BufferedAuditPort(db_path=tmp_path / "buf.db")
    for i in range(3):
        port.record(make_entry(recon_id=f"recon-{i}"))

    target = MockTarget(always_returns=True)
    drained = port.drain(target)

    assert drained == 3
    assert port.pending_count() == 0
    assert len(target.logged_events) == 3


# ---------------------------------------------------------------------------
# T4 — drain stops on False from target; partial drain
# ---------------------------------------------------------------------------


def test_drain_stops_on_false(tmp_path: Path) -> None:
    port = BufferedAuditPort(db_path=tmp_path / "buf.db")
    for i in range(5):
        port.record(make_entry(recon_id=f"recon-{i}"))

    target = MockTarget(fail_on_call=3)
    drained = port.drain(target)

    assert drained == 2
    assert port.pending_count() == 3


# ---------------------------------------------------------------------------
# T5 — drain stops on raising target; zero drained
# ---------------------------------------------------------------------------


def test_drain_stops_on_raise(tmp_path: Path) -> None:
    port = BufferedAuditPort(db_path=tmp_path / "buf.db")
    for i in range(3):
        port.record(make_entry(recon_id=f"recon-{i}"))

    target = MockTarget(raise_on_call=1)
    drained = port.drain(target)

    assert drained == 0
    assert port.pending_count() == 3


# ---------------------------------------------------------------------------
# T6 — cleanup deletes old drained rows; undrained survives
# ---------------------------------------------------------------------------


def test_cleanup_removes_old_drained_rows(tmp_path: Path) -> None:
    db = tmp_path / "buf.db"
    port = BufferedAuditPort(db_path=db)

    for i in range(3):
        port.record(make_entry(recon_id=f"recon-{i}"))

    # Manually mark first 2 as drained with an old timestamp
    conn = sqlite3.connect(str(db))
    conn.execute(
        "UPDATE audit_buffer SET drained=1, created_at='2020-01-01 00:00:00' WHERE id IN (1,2)"
    )
    conn.commit()
    conn.close()

    deleted = port.cleanup(max_age_days=14)

    assert deleted == 2
    assert port.pending_count() == 1


# ---------------------------------------------------------------------------
# T7 — record() does not raise if sqlite3.connect raises
# ---------------------------------------------------------------------------


def test_record_fail_safe_on_sqlite_error(tmp_path: Path) -> None:
    port = BufferedAuditPort(db_path=tmp_path / "buf.db")

    with patch("sqlite3.connect", side_effect=sqlite3.OperationalError("disk full")):
        # Must NOT raise
        port.record(make_entry())


# ---------------------------------------------------------------------------
# T8 — 10 threads × 10 records → pending_count == 100
# ---------------------------------------------------------------------------


def test_record_thread_safety(tmp_path: Path) -> None:
    port = BufferedAuditPort(db_path=tmp_path / "buf.db")
    barrier = threading.Barrier(10)

    def worker(thread_id: int) -> None:
        barrier.wait()
        for i in range(10):
            port.record(make_entry(recon_id=f"t{thread_id}-r{i}"))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert port.pending_count() == 100
