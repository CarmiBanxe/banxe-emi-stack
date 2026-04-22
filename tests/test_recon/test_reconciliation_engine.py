"""
tests/test_recon/test_reconciliation_engine.py — ReconciliationEngineV2 tests
IL-REC-01 | Phase 51B | Sprint 36
≥20 tests covering run_daily, breach detection, Decimal tolerance, append-only
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest

from services.recon.reconciliation_engine_v2 import (
    BREACH_HITL_THRESHOLD,
    RECON_TOLERANCE_GBP,
    HITLProposal,
    InMemoryReconStore,
    ReconciliationEngineV2,
    ReconciliationReport,
    StatementEntry,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def store() -> InMemoryReconStore:
    return InMemoryReconStore()


@pytest.fixture
def engine(store: InMemoryReconStore) -> ReconciliationEngineV2:
    return ReconciliationEngineV2(store)


def make_ledger_entry(iban: str, amount: str) -> dict:
    return {"account_iban": iban, "amount": amount}


def make_statement_entry(iban: str, amount: str, ref: str = "REF001") -> StatementEntry:
    return StatementEntry(
        entry_id="test-id",
        account_iban=iban,
        amount=Decimal(amount),
        currency="GBP",
        value_date="2026-04-21",
        description="test",
        transaction_ref=ref,
    )


# ── Constants ─────────────────────────────────────────────────────────────────


def test_recon_tolerance_is_decimal() -> None:
    assert isinstance(RECON_TOLERANCE_GBP, Decimal)
    assert Decimal("0.01") == RECON_TOLERANCE_GBP


def test_breach_hitl_threshold_is_decimal() -> None:
    assert isinstance(BREACH_HITL_THRESHOLD, Decimal)
    assert Decimal("100") == BREACH_HITL_THRESHOLD


# ── StatementEntry ────────────────────────────────────────────────────────────


def test_statement_entry_is_frozen() -> None:
    entry = make_statement_entry("GB29NWBK60161331926819", "1000.00")
    with pytest.raises(FrozenInstanceError):
        entry.amount = Decimal("999")  # type: ignore[misc]


def test_statement_entry_amount_decimal() -> None:
    entry = make_statement_entry("GB29", "500.50")
    assert isinstance(entry.amount, Decimal)
    assert entry.amount == Decimal("500.50")


def test_statement_entry_never_float() -> None:
    entry = make_statement_entry("GB29", "1000.00")
    assert not isinstance(entry.amount, float)


# ── ReconciliationItem ────────────────────────────────────────────────────────


def test_recon_item_is_frozen(engine: ReconciliationEngineV2) -> None:
    ledger = [make_ledger_entry("GB29", "1000.00")]
    stmts = [make_statement_entry("GB29", "1000.00")]
    report = engine.run_daily(date(2026, 4, 21), ledger, stmts)
    item = report.items[0]
    with pytest.raises(FrozenInstanceError):
        item.discrepancy = Decimal("999")  # type: ignore[misc]


# ── run_daily — MATCHED ───────────────────────────────────────────────────────


def test_run_daily_matched_returns_report(engine: ReconciliationEngineV2) -> None:
    ledger = [make_ledger_entry("GB29", "1000.00")]
    stmts = [make_statement_entry("GB29", "1000.00")]
    report = engine.run_daily(date(2026, 4, 21), ledger, stmts)
    assert isinstance(report, ReconciliationReport)


def test_run_daily_matched_no_breach(engine: ReconciliationEngineV2) -> None:
    ledger = [make_ledger_entry("GB29", "1000.00")]
    stmts = [make_statement_entry("GB29", "1000.00")]
    report = engine.run_daily(date(2026, 4, 21), ledger, stmts)
    assert report.breach_detected is False


def test_run_daily_matched_zero_discrepancy(engine: ReconciliationEngineV2) -> None:
    ledger = [make_ledger_entry("GB29", "1000.00")]
    stmts = [make_statement_entry("GB29", "1000.00")]
    report = engine.run_daily(date(2026, 4, 21), ledger, stmts)
    assert report.net_discrepancy_gbp == Decimal("0")


def test_run_daily_within_tolerance_not_breach(engine: ReconciliationEngineV2) -> None:
    # Discrepancy = 0.005 < RECON_TOLERANCE_GBP (0.01) → MATCHED
    ledger = [make_ledger_entry("GB29", "1000.005")]
    stmts = [make_statement_entry("GB29", "1000.000")]
    report = engine.run_daily(date(2026, 4, 21), ledger, stmts)
    assert report.breach_detected is False


def test_run_daily_item_status_matched(engine: ReconciliationEngineV2) -> None:
    ledger = [make_ledger_entry("GB29", "1000.00")]
    stmts = [make_statement_entry("GB29", "1000.00")]
    report = engine.run_daily(date(2026, 4, 21), ledger, stmts)
    assert report.items[0].status == "MATCHED"


# ── run_daily — DISCREPANCY ───────────────────────────────────────────────────


def test_run_daily_discrepancy_detected(engine: ReconciliationEngineV2) -> None:
    ledger = [make_ledger_entry("GB29", "1000.00")]
    stmts = [make_statement_entry("GB29", "500.00")]
    report = engine.run_daily(date(2026, 4, 21), ledger, stmts)
    assert report.breach_detected is True


def test_run_daily_discrepancy_item_status(engine: ReconciliationEngineV2) -> None:
    ledger = [make_ledger_entry("GB29", "1000.00")]
    stmts = [make_statement_entry("GB29", "800.00")]
    report = engine.run_daily(date(2026, 4, 21), ledger, stmts)
    assert report.items[0].status == "DISCREPANCY"


def test_run_daily_discrepancy_decimal_amounts(engine: ReconciliationEngineV2) -> None:
    ledger = [make_ledger_entry("GB29", "1000.00")]
    stmts = [make_statement_entry("GB29", "500.00")]
    report = engine.run_daily(date(2026, 4, 21), ledger, stmts)
    assert isinstance(report.net_discrepancy_gbp, Decimal)
    assert not isinstance(report.net_discrepancy_gbp, float)


# ── run_daily — MISSING entries ───────────────────────────────────────────────


def test_run_daily_missing_statement(engine: ReconciliationEngineV2) -> None:
    ledger = [make_ledger_entry("GB29", "1000.00")]
    report = engine.run_daily(date(2026, 4, 21), ledger, [])
    statuses = [i.status for i in report.items]
    assert "MISSING_STATEMENT" in statuses


def test_run_daily_missing_ledger(engine: ReconciliationEngineV2) -> None:
    stmts = [make_statement_entry("GB29", "1000.00")]
    report = engine.run_daily(date(2026, 4, 21), [], stmts)
    statuses = [i.status for i in report.items]
    assert "MISSING_LEDGER" in statuses


# ── Append-only store (I-24) ──────────────────────────────────────────────────


def test_run_daily_appends_to_store(
    engine: ReconciliationEngineV2, store: InMemoryReconStore
) -> None:
    ledger = [make_ledger_entry("GB29", "1000.00")]
    stmts = [make_statement_entry("GB29", "1000.00")]
    engine.run_daily(date(2026, 4, 21), ledger, stmts)
    assert len(store.list_reports()) == 1


def test_run_daily_multiple_appends(
    engine: ReconciliationEngineV2, store: InMemoryReconStore
) -> None:
    for i in range(3):
        ledger = [make_ledger_entry("GB29", "1000.00")]
        stmts = [make_statement_entry("GB29", "1000.00")]
        engine.run_daily(date(2026, 4, 21 - i), ledger, stmts)
    assert len(store.list_reports()) == 3


def test_store_has_no_delete_method(store: InMemoryReconStore) -> None:
    assert not hasattr(store, "delete")
    assert not hasattr(store, "remove")


def test_store_get_by_date(engine: ReconciliationEngineV2, store: InMemoryReconStore) -> None:
    ledger = [make_ledger_entry("GB29", "1000.00")]
    stmts = [make_statement_entry("GB29", "1000.00")]
    engine.run_daily(date(2026, 4, 21), ledger, stmts)
    report = store.get_by_date("2026-04-21")
    assert report is not None


def test_store_list_breaches(engine: ReconciliationEngineV2, store: InMemoryReconStore) -> None:
    ledger = [make_ledger_entry("GB29", "1000.00")]
    stmts = [make_statement_entry("GB29", "500.00")]  # breach
    engine.run_daily(date(2026, 4, 21), ledger, stmts)
    breaches = store.list_breaches()
    assert len(breaches) == 1


# ── resolve_breach → HITLProposal ─────────────────────────────────────────────


def test_resolve_breach_returns_hitl_proposal(engine: ReconciliationEngineV2) -> None:
    proposal = engine.resolve_breach("report-123", "operator_1")
    assert isinstance(proposal, HITLProposal)


def test_resolve_breach_requires_compliance_officer(engine: ReconciliationEngineV2) -> None:
    proposal = engine.resolve_breach("report-123", "operator_1")
    assert proposal.requires_approval_from == "COMPLIANCE_OFFICER"


def test_resolve_breach_autonomy_l4(engine: ReconciliationEngineV2) -> None:
    proposal = engine.resolve_breach("report-123", "operator_1")
    assert proposal.autonomy_level == "L4"


def test_resolve_breach_action_field(engine: ReconciliationEngineV2) -> None:
    proposal = engine.resolve_breach("report-123", "operator_1")
    assert proposal.action == "resolve_breach"


def test_report_amounts_all_decimal(engine: ReconciliationEngineV2) -> None:
    ledger = [make_ledger_entry("GB29", "1000.00")]
    stmts = [make_statement_entry("GB29", "999.00")]
    report = engine.run_daily(date(2026, 4, 21), ledger, stmts)
    assert isinstance(report.total_ledger_gbp, Decimal)
    assert isinstance(report.total_statement_gbp, Decimal)
    assert isinstance(report.net_discrepancy_gbp, Decimal)
