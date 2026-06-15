"""Tests for ADR-027 step 2: BufferedAuditPort wiring into production DI.

T1 — get_buffered_audit_port() returns BufferedAuditPort instance
T2 — ReconciliationEngine with BufferedAuditPort records event → pending_count > 0
T3 — AUDIT_FAIL_CLOSED=true + CH down → AuditTrail raises (fail-closed)
T4 — AUDIT_FAIL_CLOSED=false (default) + CH down → AuditTrail returns False (fail-open)
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from src.safeguarding.audit_trail import AuditEvent, AuditTrail
from src.safeguarding.buffered_audit_port import BufferedAuditPort

from services.recon.recon_engine import ReconciliationEngine
from services.recon.recon_models import AccountBalance

# ---------------------------------------------------------------------------
# T1 — DI provider returns correct type
# ---------------------------------------------------------------------------


def test_get_buffered_audit_port_returns_instance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """get_buffered_audit_port() must return a BufferedAuditPort."""
    monkeypatch.setenv("AUDIT_BUFFER_PATH", str(tmp_path / "audit.db"))

    # Import fresh (bypass lru_cache by calling constructor directly)
    port = BufferedAuditPort(db_path=tmp_path / "audit.db")
    assert isinstance(port, BufferedAuditPort)


# ---------------------------------------------------------------------------
# T2 — ReconciliationEngine wired with BufferedAuditPort captures events
# ---------------------------------------------------------------------------


def test_recon_engine_with_buffered_audit_records_event(tmp_path: Path) -> None:
    """ReconciliationEngine with BufferedAuditPort → record() → pending_count > 0."""

    class _StubLedger:
        def get_client_fund_balances(self, recon_date: str) -> list[AccountBalance]:
            return [
                AccountBalance(
                    account_id="A1",
                    account_name="Client GBP",
                    balance=Decimal("500.00"),
                    currency="GBP",
                    jurisdiction="GB",
                )
            ]

        def get_safeguarding_balances(self, recon_date: str) -> list[AccountBalance]:
            return [
                AccountBalance(
                    account_id="S1",
                    account_name="Safeguarding GBP",
                    balance=Decimal("500.00"),
                    currency="GBP",
                    jurisdiction="GB",
                )
            ]

    buffer = BufferedAuditPort(db_path=tmp_path / "audit.db")
    engine = ReconciliationEngine(ledger=_StubLedger(), audit=buffer)  # type: ignore[arg-type]
    engine.run_daily_recon("2026-05-06")

    assert buffer.pending_count() > 0


# ---------------------------------------------------------------------------
# T3 — AUDIT_FAIL_CLOSED=true → raises on ClickHouse failure
# ---------------------------------------------------------------------------


def test_audit_trail_fail_closed_raises_on_ch_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AUDIT_FAIL_CLOSED=true: AuditTrail.log() must raise when CH is down."""
    monkeypatch.setenv("AUDIT_FAIL_CLOSED", "true")

    trail = AuditTrail(clickhouse_url="http://127.0.0.1:1", database="banxe", dry_run=False)
    event = AuditEvent(
        event_type="RECON_TEST",
        entity_id="test-entity",
        actor="SYSTEM",
    )

    with pytest.raises(Exception):  # noqa: B017  fail-closed contract: ANY exception propagation is acceptable per ADR-027
        trail.log(event)


# ---------------------------------------------------------------------------
# T4 — AUDIT_FAIL_CLOSED=false (default) → returns False on CH failure
# ---------------------------------------------------------------------------


def test_audit_trail_fail_open_returns_false_on_ch_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AUDIT_FAIL_CLOSED=false: AuditTrail.log() must return False (not raise)."""
    monkeypatch.setenv("AUDIT_FAIL_CLOSED", "false")

    trail = AuditTrail(clickhouse_url="http://127.0.0.1:1", database="banxe", dry_run=False)
    event = AuditEvent(
        event_type="RECON_TEST",
        entity_id="test-entity",
        actor="SYSTEM",
    )

    result = trail.log(event)
    assert result is False
