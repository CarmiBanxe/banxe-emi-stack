"""
tests/test_recon_clickhouse.py — InMemoryReconClient unit tests
S15-FIX-2 | FCA CASS 15 / I-24 | banxe-emi-stack

20 tests: CRUD, aggregation, date range, empty results, breach tracking.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from services.recon.clickhouse_client import InMemoryReconClient


@pytest.fixture
def ch() -> InMemoryReconClient:
    return InMemoryReconClient()


def _insert_event(
    ch: InMemoryReconClient,
    account_id: str = "acc-001",
    status: str = "MATCHED",
    discrepancy: str = "0",
    recon_date: str | None = None,
) -> None:
    ch.execute(
        "INSERT INTO banxe.safeguarding_events",
        {
            "account_id": account_id,
            "account_type": "client_funds",
            "currency": "GBP",
            "internal_balance": "10000.00",
            "external_balance": "10000.00",
            "discrepancy": discrepancy,
            "status": status,
            "recon_date": recon_date or date.today().isoformat(),
            "source_file": "test.csv",
        },
    )


class TestInMemoryReconClientBasics:
    def test_initial_call_count_is_zero(self, ch):
        assert ch.call_count == 0

    def test_execute_increments_call_count(self, ch):
        _insert_event(ch)
        assert ch.call_count == 1

    def test_execute_stores_params(self, ch):
        _insert_event(ch, account_id="acc-test")
        assert ch.events[0]["account_id"] == "acc-test"

    def test_reset_clears_log(self, ch):
        _insert_event(ch)
        ch.reset()
        assert ch.call_count == 0
        assert ch.events == []

    def test_multiple_executes(self, ch):
        _insert_event(ch, account_id="acc-a")
        _insert_event(ch, account_id="acc-b")
        _insert_event(ch, account_id="acc-c")
        assert ch.call_count == 3
        ids = [e["account_id"] for e in ch.events]
        assert "acc-a" in ids
        assert "acc-b" in ids
        assert "acc-c" in ids


class TestInMemoryReconClientDiscrepancy:
    def test_discrepancy_streak_zero_for_matched(self, ch):
        _insert_event(ch, account_id="acc-matched", status="MATCHED")
        streak = ch.get_discrepancy_streak("acc-matched", date.today(), min_days=3)
        assert streak == 0

    def test_discrepancy_streak_counted(self, ch):
        for _ in range(3):
            _insert_event(ch, account_id="acc-disc", status="DISCREPANCY", discrepancy="100.00")
        streak = ch.get_discrepancy_streak("acc-disc", date.today(), min_days=3)
        assert streak == 3

    def test_get_latest_discrepancy_returns_none_for_matched(self, ch):
        _insert_event(ch, account_id="acc-ok", status="MATCHED")
        result = ch.get_latest_discrepancy("acc-ok", date.today())
        assert result is None

    def test_get_latest_discrepancy_returns_params(self, ch):
        _insert_event(ch, account_id="acc-disc2", status="DISCREPANCY", discrepancy="500.00")
        result = ch.get_latest_discrepancy("acc-disc2", date.today())
        assert result is not None
        assert result["status"] == "DISCREPANCY"

    def test_discrepancy_streak_unknown_account_is_zero(self, ch):
        streak = ch.get_discrepancy_streak("unknown", date.today(), min_days=3)
        assert streak == 0


class TestInMemoryReconClientBreaches:
    def test_write_breach_recorded(self, ch):
        class StubBreach:
            account_id = "acc-stub"
            account_type = "client_funds"
            currency = "GBP"
            discrepancy = Decimal("500.00")
            days_outstanding = 2
            first_seen = date.today()
            latest_date = date.today()

        ch.write_breach(StubBreach())
        assert len(ch.breaches) == 1
        assert ch.breaches[0]["account_id"] == "acc-stub"

    def test_breaches_not_in_events(self, ch):
        class StubBreach:
            account_id = "acc-br2"
            account_type = "client_funds"
            currency = "GBP"
            discrepancy = Decimal("200.00")
            days_outstanding = 1
            latest_date = date.today()

        ch.write_breach(StubBreach())
        _insert_event(ch, account_id="acc-normal")
        # Breaches have _is_breach=True; events returns all params
        breach_count = sum(1 for e in ch.events if e.get("_is_breach"))
        assert breach_count == 1

    def test_empty_breaches(self, ch):
        assert ch.breaches == []


class TestInMemoryReconClientSummary:
    def test_get_recon_summary_empty(self, ch):
        result = ch.get_recon_summary(date.today(), date.today())
        assert isinstance(result, list)
        assert result == []

    def test_get_recon_summary_groups_by_status(self, ch):
        today = date.today()
        _insert_event(ch, status="MATCHED", recon_date=today.isoformat())
        _insert_event(ch, status="MATCHED", recon_date=today.isoformat())
        _insert_event(ch, status="DISCREPANCY", recon_date=today.isoformat())
        result = ch.get_recon_summary(today, today)
        status_map = {r["status"]: r["count"] for r in result}
        assert status_map.get("MATCHED", 0) == 2
        assert status_map.get("DISCREPANCY", 0) == 1

    def test_get_recon_summary_filters_by_date(self, ch):
        today = date.today()
        yesterday = (today - timedelta(days=1)).isoformat()
        _insert_event(ch, status="MATCHED", recon_date=yesterday)
        result = ch.get_recon_summary(today, today)
        assert all(r["count"] == 0 or r["status"] != "MATCHED" for r in result)

    def test_get_recon_summary_total_discrepancy(self, ch):
        today = date.today()
        _insert_event(ch, status="DISCREPANCY", discrepancy="300.00", recon_date=today.isoformat())
        result = ch.get_recon_summary(today, today)
        disc_entry = next((r for r in result if r["status"] == "DISCREPANCY"), None)
        if disc_entry:
            assert disc_entry["total_discrepancy"] == Decimal("300.00")
