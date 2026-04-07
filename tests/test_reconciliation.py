"""
test_reconciliation.py — Unit tests for D-recon pipeline
IL-013 Sprint 9 | FCA CASS 7.15 | banxe-emi-stack

Tests cover:
  - ReconciliationEngine: MATCHED / DISCREPANCY / PENDING logic
  - MidazLedgerAdapter: stub adapter for balance extraction
  - ClickHouseReconClient: InMemoryReconClient captures all INSERTs
  - StatementFetcher: CSV parse + missing file → empty list
  - midaz_reconciliation: run_daily_recon dry-run pipeline

Run:
    cd /home/mmber/banxe-emi-stack
    pip install pytest httpx
    pytest tests/test_reconciliation.py -v
"""
from __future__ import annotations

import tempfile
import csv
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional


# ── Stubs ─────────────────────────────────────────────────────────────────────

class StubLedger:
    """Synchronous stub — returns preset balances by account_id."""
    def __init__(self, balances: dict):
        self._b = balances

    def get_balance(self, org_id: str, ledger_id: str, account_id: str) -> Decimal:
        return Decimal(str(self._b.get(account_id, "0")))


class InMemoryCH:
    """Captures INSERT calls for assertion in tests."""
    def __init__(self):
        self._events = []

    def execute(self, query: str, params: Optional[dict] = None) -> None:
        self._events.append(params or {})

    @property
    def events(self):
        return self._events


class StubFetcher:
    """Returns preset external balances."""
    def __init__(self, balances: list):
        self._balances = balances

    def fetch(self, recon_date: date) -> list:
        return self._balances


# ── Import under test ─────────────────────────────────────────────────────────

from services.recon.reconciliation_engine import (  # noqa: E402
    ReconciliationEngine,
    ORG_ID,
    LEDGER_ID,
)
from services.recon.statement_fetcher import StatementFetcher, StatementBalance  # noqa: E402
from services.ledger.midaz_adapter import StubLedgerAdapter  # noqa: E402
from services.recon.clickhouse_client import InMemoryReconClient  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

OPERATIONAL_ID = "019d6332-f274-709a-b3a7-983bc8745886"
CLIENT_FUNDS_ID = "019d6332-da7f-752f-b9fd-fa1c6fc777ec"
TEST_DATE = date(2026, 4, 7)


def make_engine(
    ledger_balances: dict,
    external_balances: list,
    threshold: Decimal = Decimal("1.00"),
) -> tuple[ReconciliationEngine, InMemoryReconClient]:
    ledger = StubLedger(ledger_balances)
    ch = InMemoryReconClient()
    fetcher = StubFetcher(external_balances)
    engine = ReconciliationEngine(
        ledger_port=ledger,
        ch_client=ch,
        statement_fetcher=fetcher,
        threshold=threshold,
    )
    return engine, ch


def make_ext_balance(account_id: str, balance: str) -> StatementBalance:
    return StatementBalance(
        account_id=account_id,
        currency="GBP",
        balance=Decimal(balance),
        statement_date=TEST_DATE,
        source_file="test_stmt.csv",
    )


# ── Tests: ReconciliationEngine ───────────────────────────────────────────────

class TestReconciliationEngine:

    def test_both_accounts_matched(self):
        """Internal and external balances within threshold → MATCHED."""
        engine, ch = make_engine(
            ledger_balances={
                OPERATIONAL_ID: "125000.00",
                CLIENT_FUNDS_ID: "480000.00",
            },
            external_balances=[
                make_ext_balance(OPERATIONAL_ID, "125000.00"),
                make_ext_balance(CLIENT_FUNDS_ID, "480000.50"),  # £0.50 diff — within £1.00
            ],
        )
        results = engine.reconcile(TEST_DATE)

        assert len(results) == 2
        statuses = {r.account_type: r.status for r in results}
        assert statuses["operational"] == "MATCHED"
        assert statuses["client_funds"] == "MATCHED"
        assert ch.call_count == 2

    def test_discrepancy_detected(self):
        """Difference > threshold → DISCREPANCY."""
        engine, ch = make_engine(
            ledger_balances={
                OPERATIONAL_ID: "125000.00",
                CLIENT_FUNDS_ID: "480000.00",
            },
            external_balances=[
                make_ext_balance(OPERATIONAL_ID, "125000.00"),
                make_ext_balance(CLIENT_FUNDS_ID, "481500.00"),  # £1500 diff
            ],
        )
        results = engine.reconcile(TEST_DATE)
        client_result = next(r for r in results if r.account_type == "client_funds")
        assert client_result.status == "DISCREPANCY"
        assert client_result.discrepancy == Decimal("1500.00")

    def test_pending_when_no_statement(self):
        """No external statement → PENDING (not MATCHED, not DISCREPANCY)."""
        engine, ch = make_engine(
            ledger_balances={
                OPERATIONAL_ID: "125000.00",
                CLIENT_FUNDS_ID: "480000.00",
            },
            external_balances=[],  # no statement available
        )
        results = engine.reconcile(TEST_DATE)
        assert all(r.status == "PENDING" for r in results)

    def test_threshold_boundary_exact(self):
        """Discrepancy exactly equal to threshold → MATCHED."""
        engine, ch = make_engine(
            ledger_balances={OPERATIONAL_ID: "100.00", CLIENT_FUNDS_ID: "200.00"},
            external_balances=[
                make_ext_balance(OPERATIONAL_ID, "101.00"),  # exactly £1.00 → MATCHED
                make_ext_balance(CLIENT_FUNDS_ID, "201.01"),  # £1.01 → DISCREPANCY
            ],
        )
        results = engine.reconcile(TEST_DATE)
        statuses = {r.account_type: r.status for r in results}
        assert statuses["operational"] == "MATCHED"
        assert statuses["client_funds"] == "DISCREPANCY"

    def test_all_results_written_to_clickhouse(self):
        """Every reconciliation result is written to ClickHouse."""
        engine, ch = make_engine(
            ledger_balances={OPERATIONAL_ID: "50.00", CLIENT_FUNDS_ID: "50.00"},
            external_balances=[
                make_ext_balance(OPERATIONAL_ID, "50.00"),
                make_ext_balance(CLIENT_FUNDS_ID, "50.00"),
            ],
        )
        engine.reconcile(TEST_DATE)
        assert ch.call_count == 2  # one INSERT per account

    def test_decimal_amounts_not_float(self):
        """All balance values must be Decimal (FCA I-24)."""
        engine, ch = make_engine(
            ledger_balances={OPERATIONAL_ID: "125000.01", CLIENT_FUNDS_ID: "480000.99"},
            external_balances=[
                make_ext_balance(OPERATIONAL_ID, "125000.01"),
                make_ext_balance(CLIENT_FUNDS_ID, "480000.99"),
            ],
        )
        results = engine.reconcile(TEST_DATE)
        for r in results:
            assert isinstance(r.internal_balance, Decimal), "internal_balance must be Decimal"
            assert isinstance(r.external_balance, Decimal), "external_balance must be Decimal"
            assert isinstance(r.discrepancy, Decimal), "discrepancy must be Decimal"


# ── Tests: StubLedgerAdapter ──────────────────────────────────────────────────

class TestStubLedgerAdapter:

    def test_returns_preset_balance(self):
        adapter = StubLedgerAdapter({OPERATIONAL_ID: Decimal("99999.00")})
        result = adapter.get_balance("org", "ledger", OPERATIONAL_ID)
        assert result == Decimal("99999.00")

    def test_returns_zero_for_unknown_account(self):
        adapter = StubLedgerAdapter({})
        result = adapter.get_balance("org", "ledger", "unknown-id")
        assert result == Decimal("0")


# ── Tests: InMemoryReconClient ────────────────────────────────────────────────

class TestInMemoryReconClient:

    def test_captures_events(self):
        ch = InMemoryReconClient()
        ch.execute("INSERT INTO ...", {"status": "MATCHED", "discrepancy": 0.0})
        ch.execute("INSERT INTO ...", {"status": "DISCREPANCY", "discrepancy": 500.0})
        assert ch.call_count == 2
        assert ch.events[0]["status"] == "MATCHED"
        assert ch.events[1]["status"] == "DISCREPANCY"

    def test_reset_clears_log(self):
        ch = InMemoryReconClient()
        ch.execute("INSERT ...", {"x": 1})
        ch.reset()
        assert ch.call_count == 0


# ── Tests: StatementFetcher ───────────────────────────────────────────────────

class TestStatementFetcher:

    def test_csv_parse_returns_balances(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "stmt_20260407.csv"
            with csv_path.open("w", newline="") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=["account_id", "currency", "balance", "statement_date", "source_file"],
                )
                writer.writeheader()
                writer.writerow({
                    "account_id": OPERATIONAL_ID,
                    "currency": "GBP",
                    "balance": "125000.00",
                    "statement_date": "2026-04-07",
                    "source_file": "stmt_20260407.csv",
                })

            fetcher = StatementFetcher(statement_dir=tmpdir)
            balances = fetcher._fetch_csv(date(2026, 4, 7))

            assert len(balances) == 1
            assert balances[0].account_id == OPERATIONAL_ID
            assert balances[0].balance == Decimal("125000.00")
            assert isinstance(balances[0].balance, Decimal)

    def test_missing_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fetcher = StatementFetcher(statement_dir=tmpdir)
            result = fetcher._fetch_csv(date(2026, 4, 7))
            assert result == []


# ── Tests: midaz_reconciliation dry-run ──────────────────────────────────────

class TestDryRunPipeline:
    """
    Smoke test for run_daily_recon() in dry-run mode.
    Requires env vars for Midaz (can be stubs since we mock below).
    """

    def test_dry_run_returns_summary_dict(self, monkeypatch):
        """dry_run=True → returns summary dict, no ClickHouse writes."""
        # Patch MidazLedgerAdapter to use stub
        from services.ledger import midaz_adapter
        monkeypatch.setattr(
            midaz_adapter,
            "MidazLedgerAdapter",
            lambda: StubLedgerAdapter({
                OPERATIONAL_ID: Decimal("125000.00"),
                CLIENT_FUNDS_ID: Decimal("480000.00"),
            }),
        )

        # Set required env vars
        monkeypatch.setenv("MIDAZ_BASE_URL", "http://localhost:8095")
        monkeypatch.setenv("MIDAZ_ORG_ID", ORG_ID)
        monkeypatch.setenv("MIDAZ_LEDGER_ID", LEDGER_ID)
        monkeypatch.setenv("STATEMENT_DIR", "/tmp/banxe_test_statements")

        from services.recon.midaz_reconciliation import run_daily_recon
        summary = run_daily_recon(recon_date=TEST_DATE, dry_run=True)

        assert "recon_date" in summary
        assert summary["recon_date"] == "2026-04-07"
        assert summary["total_accounts"] == 2
        assert "overall_status" in summary
        assert summary["overall_status"] in {"MATCHED", "PENDING", "DISCREPANCY"}
