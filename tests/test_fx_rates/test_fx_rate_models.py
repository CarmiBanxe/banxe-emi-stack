"""Tests for fx_rate_models.py — RateEntry, ConversionResult, InMemoryRateStore.

IL-FXR-01 | Phase 52A | Sprint 37
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from services.fx_rates.fx_rate_models import (
    ConversionResult,
    InMemoryRateStore,
    RateEntry,
    RateOverride,
    RateStorePort,
)

# ── RateEntry ──────────────────────────────────────────────────────────────


def test_rate_entry_is_frozen_dataclass() -> None:
    entry = RateEntry(base="GBP", date="2026-01-01", rates={"EUR": "1.165"})
    with pytest.raises((FrozenInstanceError, AttributeError)):
        entry.base = "USD"  # type: ignore[misc]


def test_rate_entry_default_source() -> None:
    entry = RateEntry(base="GBP", date="2026-01-01", rates={})
    assert entry.source == "frankfurter-ecb"


def test_rate_entry_rates_are_strings() -> None:
    """Rates stored as strings (JSON-safe, I-01)."""
    entry = RateEntry(base="GBP", date="2026-01-01", rates={"EUR": "1.1650"})
    assert isinstance(entry.rates["EUR"], str)


def test_rate_entry_custom_fetched_at() -> None:
    entry = RateEntry(base="EUR", date="2026-01-01", rates={}, fetched_at="2026-01-01T07:00:00Z")
    assert entry.fetched_at == "2026-01-01T07:00:00Z"


def test_rate_entry_empty_rates_allowed() -> None:
    entry = RateEntry(base="GBP", date="2026-01-01", rates={})
    assert entry.rates == {}


def test_rate_entry_multiple_symbols() -> None:
    rates = {"EUR": "1.165", "USD": "1.234", "JPY": "185.5"}
    entry = RateEntry(base="GBP", date="2026-01-01", rates=rates)
    assert len(entry.rates) == 3


# ── ConversionResult ───────────────────────────────────────────────────────


def test_conversion_result_is_frozen() -> None:
    result = ConversionResult(
        from_currency="GBP",
        to_currency="EUR",
        amount=Decimal("100"),
        converted_amount=Decimal("116.50"),
        rate=Decimal("1.165"),
        date="2026-01-01",
    )
    with pytest.raises((FrozenInstanceError, AttributeError)):
        result.from_currency = "USD"  # type: ignore[misc]


def test_conversion_result_amounts_are_decimal() -> None:
    """I-01: All amounts must be Decimal."""
    result = ConversionResult(
        from_currency="GBP",
        to_currency="EUR",
        amount=Decimal("100.00"),
        converted_amount=Decimal("116.5000"),
        rate=Decimal("1.1650"),
        date="2026-01-01",
    )
    assert isinstance(result.amount, Decimal)
    assert isinstance(result.converted_amount, Decimal)
    assert isinstance(result.rate, Decimal)


def test_conversion_result_not_float() -> None:
    """I-01: Never use float for money."""
    result = ConversionResult(
        from_currency="GBP",
        to_currency="EUR",
        amount=Decimal("50.00"),
        converted_amount=Decimal("58.25"),
        rate=Decimal("1.165"),
        date="2026-01-01",
    )
    assert not isinstance(result.amount, float)
    assert not isinstance(result.converted_amount, float)


# ── RateOverride ───────────────────────────────────────────────────────────


def test_rate_override_is_frozen() -> None:
    override = RateOverride(
        override_id="ovr_abc123",
        base="GBP",
        symbol="EUR",
        rate=Decimal("1.20"),
        operator="ops@banxe.com",
        reason="Test override",
        created_at="2026-01-01T00:00:00Z",
    )
    with pytest.raises((FrozenInstanceError, AttributeError)):
        override.rate = Decimal("1.30")  # type: ignore[misc]


def test_rate_override_rate_is_decimal() -> None:
    """I-01: Override rate must be Decimal."""
    override = RateOverride(
        override_id="ovr_test",
        base="GBP",
        symbol="EUR",
        rate=Decimal("1.25"),
        operator="ops@banxe.com",
        reason="Test",
        created_at="2026-01-01T00:00:00Z",
    )
    assert isinstance(override.rate, Decimal)


# ── InMemoryRateStore ──────────────────────────────────────────────────────


def test_in_memory_rate_store_seeded_on_init() -> None:
    store = InMemoryRateStore()
    gbp = store.get_latest("GBP")
    assert gbp is not None
    assert gbp.base == "GBP"


def test_in_memory_rate_store_seeded_eur() -> None:
    store = InMemoryRateStore()
    eur = store.get_latest("EUR")
    assert eur is not None
    assert eur.base == "EUR"


def test_in_memory_rate_store_append() -> None:
    """I-24: append-only store."""
    store = InMemoryRateStore()
    initial_count = len(store.list_recent(100))
    entry = RateEntry(base="USD", date="2026-01-01", rates={"EUR": "0.95"})
    store.append(entry)
    assert len(store.list_recent(100)) == initial_count + 1


def test_in_memory_rate_store_get_latest_returns_last() -> None:
    store = InMemoryRateStore()
    entry1 = RateEntry(base="TEST", date="2026-01-01", rates={"EUR": "1.0"})
    entry2 = RateEntry(base="TEST", date="2026-01-02", rates={"EUR": "1.1"})
    store.append(entry1)
    store.append(entry2)
    latest = store.get_latest("TEST")
    assert latest is not None
    assert latest.date == "2026-01-02"


def test_in_memory_rate_store_get_latest_missing() -> None:
    store = InMemoryRateStore()
    result = store.get_latest("XYZ")
    assert result is None


def test_in_memory_rate_store_get_historical() -> None:
    store = InMemoryRateStore()
    entry = RateEntry(base="GBP", date="2025-12-01", rates={"EUR": "1.15"})
    store.append(entry)
    found = store.get_historical("GBP", "2025-12-01")
    assert found is not None
    assert found.date == "2025-12-01"


def test_in_memory_rate_store_get_historical_not_found() -> None:
    store = InMemoryRateStore()
    result = store.get_historical("GBP", "1900-01-01")
    assert result is None


def test_in_memory_rate_store_list_recent_limit() -> None:
    store = InMemoryRateStore()
    for i in range(10):
        store.append(RateEntry(base="LIMIT", date=f"2026-01-{i + 1:02d}", rates={}))
    recent = store.list_recent(limit=5)
    assert len(recent) == 5


def test_in_memory_rate_store_list_recent_default_30() -> None:
    store = InMemoryRateStore()
    # seed has 2 entries, add 5 more
    for i in range(5):
        store.append(RateEntry(base="X", date=f"2026-01-{i + 1:02d}", rates={}))
    recent = store.list_recent()
    assert len(recent) <= 30


def test_rate_store_port_protocol_satisfied() -> None:
    """InMemoryRateStore satisfies RateStorePort protocol."""
    store: RateStorePort = InMemoryRateStore()
    assert callable(store.append)
    assert callable(store.get_latest)
    assert callable(store.get_historical)
    assert callable(store.list_recent)


def test_rate_entry_gbp_seed_has_eur() -> None:
    store = InMemoryRateStore()
    gbp = store.get_latest("GBP")
    assert gbp is not None
    assert "EUR" in gbp.rates


def test_rate_entry_gbp_seed_rates_are_decimal_convertible() -> None:
    """I-01: Seeded rates should be convertible to Decimal."""
    store = InMemoryRateStore()
    gbp = store.get_latest("GBP")
    assert gbp is not None
    for sym, rate_str in gbp.rates.items():
        d = Decimal(rate_str)
        assert d > 0
