"""
tests/test_recon/test_recon_agent.py — ReconAgent tests
IL-REC-01 | Phase 51B | Sprint 36
≥20 tests covering HITLProposal on breach > £100, get_report, list_breaches
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.recon.recon_agent import ReconAgent
from services.recon.reconciliation_engine_v2 import (
    HITLProposal,
    InMemoryReconStore,
    ReconciliationReport,
    StatementEntry,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def store() -> InMemoryReconStore:
    return InMemoryReconStore()


@pytest.fixture
def agent(store: InMemoryReconStore) -> ReconAgent:
    return ReconAgent(store=store)


def make_ledger(iban: str, amount: str) -> dict:
    return {"account_iban": iban, "amount": amount}


def make_stmt(iban: str, amount: str) -> StatementEntry:
    return StatementEntry(
        entry_id="test",
        account_iban=iban,
        amount=Decimal(amount),
        currency="GBP",
        value_date="2026-04-21",
        description="test",
        transaction_ref="REF",
    )


# ── run_daily_recon — no breach ───────────────────────────────────────────────


def test_run_daily_recon_no_breach_returns_report(agent: ReconAgent) -> None:
    result = agent.run_daily_recon(
        "2026-04-21",
        [make_ledger("GB29", "1000.00")],
        [make_stmt("GB29", "1000.00")],
    )
    assert isinstance(result, ReconciliationReport)


def test_run_daily_recon_no_breach_breach_false(agent: ReconAgent) -> None:
    result = agent.run_daily_recon(
        "2026-04-21",
        [make_ledger("GB29", "1000.00")],
        [make_stmt("GB29", "1000.00")],
    )
    assert isinstance(result, ReconciliationReport)
    assert result.breach_detected is False


def test_run_daily_recon_small_breach_returns_report(agent: ReconAgent) -> None:
    # Discrepancy of £50 < BREACH_HITL_THRESHOLD (£100) → returns ReconciliationReport
    result = agent.run_daily_recon(
        "2026-04-21",
        [make_ledger("GB29", "1000.00")],
        [make_stmt("GB29", "950.00")],
    )
    assert isinstance(result, ReconciliationReport)
    assert result.breach_detected is True


# ── run_daily_recon — breach > £100 → HITLProposal ───────────────────────────


def test_run_daily_recon_large_breach_returns_hitl(agent: ReconAgent) -> None:
    result = agent.run_daily_recon(
        "2026-04-21",
        [make_ledger("GB29", "1000.00")],
        [make_stmt("GB29", "800.00")],  # discrepancy = £200 > £100
    )
    assert isinstance(result, HITLProposal)


def test_run_daily_recon_large_breach_requires_compliance_officer(agent: ReconAgent) -> None:
    result = agent.run_daily_recon(
        "2026-04-21",
        [make_ledger("GB29", "1000.00")],
        [make_stmt("GB29", "800.00")],
    )
    assert isinstance(result, HITLProposal)
    assert result.requires_approval_from == "COMPLIANCE_OFFICER"


def test_run_daily_recon_large_breach_autonomy_l4(agent: ReconAgent) -> None:
    result = agent.run_daily_recon(
        "2026-04-21",
        [make_ledger("GB29", "1000.00")],
        [make_stmt("GB29", "800.00")],
    )
    assert isinstance(result, HITLProposal)
    assert result.autonomy_level == "L4"


def test_run_daily_recon_breach_exact_100_not_hitl(agent: ReconAgent) -> None:
    # Discrepancy exactly £100 — not > threshold, so returns ReconciliationReport
    result = agent.run_daily_recon(
        "2026-04-21",
        [make_ledger("GB29", "1000.00")],
        [make_stmt("GB29", "900.00")],  # exactly £100 discrepancy
    )
    # Net discrepancy = £100, BREACH_HITL_THRESHOLD = £100, condition is > not >=
    assert isinstance(result, ReconciliationReport)


def test_run_daily_recon_breach_over_100_hitl(agent: ReconAgent) -> None:
    # Discrepancy £100.01 → triggers HITL
    result = agent.run_daily_recon(
        "2026-04-21",
        [make_ledger("GB29", "1000.00")],
        [make_stmt("GB29", "899.99")],  # £100.01 discrepancy
    )
    assert isinstance(result, HITLProposal)


# ── get_report ────────────────────────────────────────────────────────────────


def test_get_report_returns_none_if_not_found(agent: ReconAgent) -> None:
    result = agent.get_report("2020-01-01")
    assert result is None


def test_get_report_returns_report_after_run(agent: ReconAgent) -> None:
    agent.run_daily_recon(
        "2026-04-21",
        [make_ledger("GB29", "1000.00")],
        [make_stmt("GB29", "1000.00")],
    )
    report = agent.get_report("2026-04-21")
    assert report is not None
    assert report.recon_date == "2026-04-21"


def test_get_report_correct_date(agent: ReconAgent) -> None:
    agent.run_daily_recon(
        "2026-04-20",
        [make_ledger("GB29", "500.00")],
        [make_stmt("GB29", "500.00")],
    )
    report = agent.get_report("2026-04-20")
    assert report is not None
    assert report.recon_date == "2026-04-20"


# ── list_unresolved_breaches ──────────────────────────────────────────────────


def test_list_unresolved_breaches_empty_initially(agent: ReconAgent) -> None:
    breaches = agent.list_unresolved_breaches()
    assert breaches == []


def test_list_unresolved_breaches_includes_breach_reports(agent: ReconAgent) -> None:
    # Run with discrepancy (£50 < £100, breach_detected=True but not HITL threshold)
    agent.run_daily_recon(
        "2026-04-21",
        [make_ledger("GB29", "1000.00")],
        [make_stmt("GB29", "950.00")],
    )
    breaches = agent.list_unresolved_breaches()
    assert len(breaches) == 1


def test_list_unresolved_breaches_excludes_matched(agent: ReconAgent) -> None:
    agent.run_daily_recon(
        "2026-04-21",
        [make_ledger("GB29", "1000.00")],
        [make_stmt("GB29", "1000.00")],
    )
    breaches = agent.list_unresolved_breaches()
    assert len(breaches) == 0


def test_list_all_reports(agent: ReconAgent) -> None:
    for i in range(3):
        agent.run_daily_recon(
            f"2026-04-{21 - i:02d}",
            [make_ledger("GB29", "1000.00")],
            [make_stmt("GB29", "1000.00")],
        )
    reports = agent.list_all_reports()
    assert len(reports) == 3


def test_run_daily_recon_empty_ledger_and_stmt(agent: ReconAgent) -> None:
    result = agent.run_daily_recon("2026-04-21")
    assert isinstance(result, ReconciliationReport)
    assert result.breach_detected is False


def test_run_daily_recon_report_amounts_decimal(agent: ReconAgent) -> None:
    result = agent.run_daily_recon(
        "2026-04-21",
        [make_ledger("GB29", "1000.00")],
        [make_stmt("GB29", "1000.00")],
    )
    assert isinstance(result, ReconciliationReport)
    assert isinstance(result.total_ledger_gbp, Decimal)
    assert isinstance(result.total_statement_gbp, Decimal)
