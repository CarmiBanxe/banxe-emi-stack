"""tests/test_multi_currency/test_conversion_tracker.py — ConversionTracker tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.multi_currency.conversion_tracker import _CONVERSION_FEE_RATE, ConversionTracker
from services.multi_currency.models import (
    ConversionStatus,
    InMemoryConversionStore,
    InMemoryLedgerEntryStore,
    InMemoryMCAudit,
)


def _make_tracker() -> ConversionTracker:
    return ConversionTracker(
        conversion_store=InMemoryConversionStore(),
        ledger_store=InMemoryLedgerEntryStore(),
        audit=InMemoryMCAudit(),
    )


# ── fee rate constant ──────────────────────────────────────────────────────────


def test_conversion_fee_rate_is_0_2_percent() -> None:
    assert Decimal("0.002") == _CONVERSION_FEE_RATE


# ── record_conversion ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_conversion_returns_record() -> None:
    tracker = _make_tracker()
    record = await tracker.record_conversion(
        "mc-001", "GBP", "EUR", Decimal("100"), Decimal("116"), Decimal("1.16")
    )
    assert record.account_id == "mc-001"
    assert record.from_currency == "GBP"
    assert record.to_currency == "EUR"


@pytest.mark.asyncio
async def test_record_conversion_status_completed() -> None:
    tracker = _make_tracker()
    record = await tracker.record_conversion(
        "mc-001", "GBP", "EUR", Decimal("100"), Decimal("116"), Decimal("1.16")
    )
    assert record.status == ConversionStatus.COMPLETED


@pytest.mark.asyncio
async def test_record_conversion_fee_is_0_2_percent() -> None:
    tracker = _make_tracker()
    from_amount = Decimal("500")
    record = await tracker.record_conversion(
        "mc-001", "GBP", "EUR", from_amount, Decimal("580"), Decimal("1.16")
    )
    expected_fee = from_amount * Decimal("0.002")
    assert record.fee == expected_fee


@pytest.mark.asyncio
async def test_record_conversion_fee_uses_decimal() -> None:
    tracker = _make_tracker()
    record = await tracker.record_conversion(
        "mc-001", "GBP", "USD", Decimal("1000"), Decimal("1270"), Decimal("1.27")
    )
    assert isinstance(record.fee, Decimal)


@pytest.mark.asyncio
async def test_record_conversion_assigns_unique_id() -> None:
    tracker = _make_tracker()
    r1 = await tracker.record_conversion(
        "mc-001", "GBP", "EUR", Decimal("100"), Decimal("116"), Decimal("1.16")
    )
    r2 = await tracker.record_conversion(
        "mc-001", "GBP", "EUR", Decimal("100"), Decimal("116"), Decimal("1.16")
    )
    assert r1.conversion_id != r2.conversion_id


# ── get_conversion ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_conversion_returns_record() -> None:
    tracker = _make_tracker()
    record = await tracker.record_conversion(
        "mc-001", "GBP", "EUR", Decimal("100"), Decimal("116"), Decimal("1.16")
    )
    fetched = await tracker.get_conversion(record.conversion_id)
    assert fetched is not None
    assert fetched.conversion_id == record.conversion_id


@pytest.mark.asyncio
async def test_get_conversion_unknown_returns_none() -> None:
    tracker = _make_tracker()
    result = await tracker.get_conversion("nonexistent")
    assert result is None


# ── list_conversions ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_conversions_returns_account_records() -> None:
    tracker = _make_tracker()
    await tracker.record_conversion(
        "mc-001", "GBP", "EUR", Decimal("100"), Decimal("116"), Decimal("1.16")
    )
    await tracker.record_conversion(
        "mc-001", "EUR", "USD", Decimal("50"), Decimal("55"), Decimal("1.10")
    )
    records = await tracker.list_conversions("mc-001")
    assert len(records) == 2


@pytest.mark.asyncio
async def test_list_conversions_filters_by_account() -> None:
    tracker = _make_tracker()
    await tracker.record_conversion(
        "mc-001", "GBP", "EUR", Decimal("100"), Decimal("116"), Decimal("1.16")
    )
    await tracker.record_conversion(
        "mc-002", "GBP", "EUR", Decimal("200"), Decimal("232"), Decimal("1.16")
    )
    records = await tracker.list_conversions("mc-001")
    assert len(records) == 1


# ── get_conversion_summary ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_conversion_summary_total_conversions() -> None:
    tracker = _make_tracker()
    await tracker.record_conversion(
        "mc-001", "GBP", "EUR", Decimal("100"), Decimal("116"), Decimal("1.16")
    )
    await tracker.record_conversion(
        "mc-001", "EUR", "USD", Decimal("50"), Decimal("55"), Decimal("1.10")
    )
    summary = await tracker.get_conversion_summary("mc-001")
    assert summary["total_conversions"] == 2


@pytest.mark.asyncio
async def test_conversion_summary_total_fees() -> None:
    tracker = _make_tracker()
    await tracker.record_conversion(
        "mc-001", "GBP", "EUR", Decimal("100"), Decimal("116"), Decimal("1.16")
    )
    summary = await tracker.get_conversion_summary("mc-001")
    expected_fee = Decimal("100") * Decimal("0.002")
    assert Decimal(summary["total_fees"]) == expected_fee


@pytest.mark.asyncio
async def test_conversion_summary_currencies_used() -> None:
    tracker = _make_tracker()
    await tracker.record_conversion(
        "mc-001", "GBP", "EUR", Decimal("100"), Decimal("116"), Decimal("1.16")
    )
    summary = await tracker.get_conversion_summary("mc-001")
    assert "GBP" in summary["currencies_used"]
    assert "EUR" in summary["currencies_used"]


@pytest.mark.asyncio
async def test_conversion_summary_empty_account() -> None:
    tracker = _make_tracker()
    summary = await tracker.get_conversion_summary("mc-empty")
    assert summary["total_conversions"] == 0
    assert summary["total_fees"] == "0"
    assert summary["currencies_used"] == []
