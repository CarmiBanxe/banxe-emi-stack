"""
tests/test_recon_failclosed.py — ReconciliationEngine fail-closed behaviour.

D-gl build-spec DoD #8 consumer side: when the internal ledger (Midaz) is
unavailable, ``get_balance`` now raises ``LedgerInfrastructureError`` instead of
returning a silent ``Decimal("0")``. The recon engine must surface this as an
ERROR result — it must NEVER let a masked zero balance become a false MATCHED
tie-out against an external statement of 0.

All offline — no live Midaz, no ClickHouse.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from services.ledger.ledger_port import LedgerInfrastructureError
from services.recon.reconciliation_engine import (
    SAFEGUARDING_ACCOUNTS,
    ReconciliationEngine,
)

ACCOUNT_IDS = list(SAFEGUARDING_ACCOUNTS.keys())


@dataclass(frozen=True)
class _ExtBalance:
    account_id: str
    balance: Decimal
    currency: str = "GBP"
    source_file: str = "stmt.csv"


class _UnavailableLedger:
    """LedgerPort whose get_balance always fails closed (Midaz unreachable)."""

    def get_balance(self, org_id: str, ledger_id: str, account_id: str) -> Decimal:
        raise LedgerInfrastructureError(f"Midaz unavailable for {account_id}")


class _FakeCH:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def execute(self, _sql: str, params: dict) -> None:
        self.rows.append(params)


class _FakeFetcher:
    def __init__(self, balances: list[_ExtBalance]) -> None:
        self._balances = balances

    def fetch(self, _recon_date: date) -> list[_ExtBalance]:
        return self._balances


def _engine(fetcher: _FakeFetcher) -> ReconciliationEngine:
    return ReconciliationEngine(
        ledger_port=_UnavailableLedger(),
        ch_client=_FakeCH(),
        statement_fetcher=fetcher,
    )


def test_recon_infra_error_yields_error_status_not_match():
    """External 0 present + internal unavailable → ERROR, never a false MATCHED."""
    external = [_ExtBalance(account_id=aid, balance=Decimal("0")) for aid in ACCOUNT_IDS]
    results = _engine(_FakeFetcher(external)).reconcile(date(2026, 6, 26))

    assert results, "expected one result per safeguarding account"
    assert all(r.status == "ERROR" for r in results)
    assert not any(r.status in {"MATCHED", "DISCREPANCY"} for r in results)


def test_recon_infra_error_no_external_statement_still_error():
    """Even with no external statement, infra failure is ERROR (not PENDING)."""
    results = _engine(_FakeFetcher([])).reconcile(date(2026, 6, 26))
    assert all(r.status == "ERROR" for r in results)
    assert not any(r.status == "PENDING" for r in results)


def test_recon_error_result_is_surfaced_to_clickhouse():
    """Fail-closed ERROR rows are still written out (surfaced, not swallowed)."""
    ch = _FakeCH()
    engine = ReconciliationEngine(
        ledger_port=_UnavailableLedger(),
        ch_client=ch,
        statement_fetcher=_FakeFetcher([]),
    )
    engine.reconcile(date(2026, 6, 26))
    assert ch.rows, "ERROR results must be persisted (surfaced), not dropped"
    assert all(row["status"] == "ERROR" for row in ch.rows)
