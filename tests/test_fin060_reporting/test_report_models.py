"""
tests/test_fin060_reporting/test_report_models.py — FIN060 report models tests
IL-FIN060-01 | Phase 51C | Sprint 36
≥20 tests covering FIN060Entry, FIN060Report, InMemoryReportStore
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from services.reporting.report_models import (
    FIN060Entry,
    FIN060Report,
    InMemoryReportStore,
)


def make_entry(account_type: str = "safeguarding", balance: str = "100000.00") -> FIN060Entry:
    return FIN060Entry(
        entry_id="entry001",
        account_type=account_type,
        currency="GBP",
        balance=Decimal(balance),
        period_start="2026-04-01",
        period_end="2026-04-30",
    )


def make_report(month: int = 4, year: int = 2026, status: str = "DRAFT") -> FIN060Report:
    return FIN060Report(
        report_id="rpt001",
        month=month,
        year=year,
        total_safeguarded_gbp=Decimal("100000.00"),
        total_operational_gbp=Decimal("50000.00"),
        entries=(),
        status=status,
        generated_at="2026-04-21T00:00:00+00:00",
    )


# ── FIN060Entry ───────────────────────────────────────────────────────────────


def test_fin060_entry_is_frozen() -> None:
    entry = make_entry()
    with pytest.raises(FrozenInstanceError):
        entry.balance = Decimal("999")  # type: ignore[misc]


def test_fin060_entry_balance_is_decimal() -> None:
    entry = make_entry(balance="100000.00")
    assert isinstance(entry.balance, Decimal)


def test_fin060_entry_balance_never_float() -> None:
    entry = make_entry(balance="100000.00")
    assert not isinstance(entry.balance, float)


def test_fin060_entry_account_type() -> None:
    entry = make_entry("safeguarding")
    assert entry.account_type == "safeguarding"


def test_fin060_entry_operational_type() -> None:
    entry = make_entry("operational")
    assert entry.account_type == "operational"


def test_fin060_entry_currency() -> None:
    entry = make_entry()
    assert entry.currency == "GBP"


# ── FIN060Report ──────────────────────────────────────────────────────────────


def test_fin060_report_is_frozen() -> None:
    report = make_report()
    with pytest.raises(FrozenInstanceError):
        report.status = "APPROVED"  # type: ignore[misc]


def test_fin060_report_total_safeguarded_is_decimal() -> None:
    report = make_report()
    assert isinstance(report.total_safeguarded_gbp, Decimal)


def test_fin060_report_total_operational_is_decimal() -> None:
    report = make_report()
    assert isinstance(report.total_operational_gbp, Decimal)


def test_fin060_report_never_float() -> None:
    report = make_report()
    assert not isinstance(report.total_safeguarded_gbp, float)
    assert not isinstance(report.total_operational_gbp, float)


def test_fin060_report_status_draft() -> None:
    report = make_report(status="DRAFT")
    assert report.status == "DRAFT"


def test_fin060_report_approved_by_none() -> None:
    report = make_report()
    assert report.approved_by is None


def test_fin060_report_month_year() -> None:
    report = make_report(month=4, year=2026)
    assert report.month == 4
    assert report.year == 2026


def test_fin060_report_entries_tuple() -> None:
    entry = make_entry()
    report = FIN060Report(
        report_id="rpt001",
        month=4,
        year=2026,
        total_safeguarded_gbp=Decimal("100000.00"),
        total_operational_gbp=Decimal("50000.00"),
        entries=(entry,),
        status="DRAFT",
        generated_at="2026-04-21T00:00:00+00:00",
    )
    assert len(report.entries) == 1
    assert report.entries[0] is entry


# ── InMemoryReportStore ───────────────────────────────────────────────────────


def test_store_initially_empty() -> None:
    store = InMemoryReportStore()
    assert store.list_reports() == []


def test_store_append_increases_count() -> None:
    store = InMemoryReportStore()
    store.append(make_report())
    assert len(store.list_reports()) == 1


def test_store_append_multiple() -> None:
    store = InMemoryReportStore()
    for m in range(1, 4):
        store.append(make_report(month=m))
    assert len(store.list_reports()) == 3


def test_store_get_by_period_found() -> None:
    store = InMemoryReportStore()
    store.append(make_report(month=4, year=2026))
    report = store.get_by_period(4, 2026)
    assert report is not None
    assert report.month == 4
    assert report.year == 2026


def test_store_get_by_period_not_found() -> None:
    store = InMemoryReportStore()
    report = store.get_by_period(1, 2020)
    assert report is None


def test_store_has_no_delete_method() -> None:
    store = InMemoryReportStore()
    assert not hasattr(store, "delete")
    assert not hasattr(store, "remove")


def test_store_list_returns_copy() -> None:
    store = InMemoryReportStore()
    store.append(make_report())
    reports = store.list_reports()
    reports.clear()
    assert len(store.list_reports()) == 1
