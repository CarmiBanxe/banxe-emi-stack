"""InMemoryDataQualityPort unit tests — 100% coverage over services/data_quality/data_quality_port.py.

Validates: happy-path reads for all 4 methods, failure paths (fail_on_call=True),
unknown dataset raises DataQualityPortError, custom seed data injection, value type
invariants (I-01: Decimal for numeric metrics, frozen=True on DTOs), and port
abstractness.

asyncio_mode = "auto" (pyproject.toml): every ``async def test_*`` is auto-collected
without @pytest.mark.asyncio.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from services.data_quality.data_quality_port import (
    DataQualityPort,
    DataQualityPortError,
    DataQualityReport,
    DriftSignal,
    InMemoryDataQualityPort,
)

# ---------------------------------------------------------------------------
# Happy path — default seed data
# ---------------------------------------------------------------------------


async def test_get_drift_score_returns_correct_type() -> None:
    """Default seed returns DriftSignal with Decimal drift_score (I-01)."""
    port = InMemoryDataQualityPort()
    result = await port.get_drift_score("payments")

    assert isinstance(result, DriftSignal)
    assert isinstance(result.drift_score, Decimal)
    assert result.dataset == "payments"
    assert isinstance(result.as_of, str)
    assert len(result.as_of) > 0


async def test_get_quality_report_returns_correct_type() -> None:
    """Default seed returns DataQualityReport with Decimal numeric fields (I-01)."""
    port = InMemoryDataQualityPort()
    result = await port.get_quality_report("payments")

    assert isinstance(result, DataQualityReport)
    assert isinstance(result.null_rate, Decimal)
    assert isinstance(result.schema_conformance, Decimal)
    assert isinstance(result.drift_score, Decimal)
    assert isinstance(result.freshness_seconds, int)
    assert result.dataset == "payments"
    assert isinstance(result.as_of, str)


async def test_list_datasets_returns_nonempty_list() -> None:
    """Default seed returns a non-empty list of dataset name strings."""
    port = InMemoryDataQualityPort()
    result = await port.list_datasets()

    assert isinstance(result, list)
    assert len(result) >= 1
    assert all(isinstance(name, str) for name in result)


async def test_get_freshness_returns_int() -> None:
    """Default seed returns an integer freshness_seconds."""
    port = InMemoryDataQualityPort()
    result = await port.get_freshness("payments")

    assert isinstance(result, int)
    assert result >= 0


async def test_second_dataset_readable() -> None:
    """Default seed exposes at least two datasets (payments + customers)."""
    port = InMemoryDataQualityPort()
    signal = await port.get_drift_score("customers")
    report = await port.get_quality_report("customers")
    freshness = await port.get_freshness("customers")

    assert signal.dataset == "customers"
    assert isinstance(signal.drift_score, Decimal)
    assert report.dataset == "customers"
    assert isinstance(freshness, int)


# ---------------------------------------------------------------------------
# Custom seed data
# ---------------------------------------------------------------------------


async def test_custom_signal_seed_returned_unchanged() -> None:
    """Custom DriftSignal seed is returned exactly as injected."""
    custom = DriftSignal(dataset="trades", drift_score=Decimal("0.15"), as_of="2026-01-01")
    port = InMemoryDataQualityPort(signals={"trades": custom})
    result = await port.get_drift_score("trades")
    assert result is custom


async def test_custom_report_seed_returned_unchanged() -> None:
    """Custom DataQualityReport seed is returned exactly as injected."""
    custom = DataQualityReport(
        dataset="trades",
        null_rate=Decimal("0.02"),
        schema_conformance=Decimal("0.98"),
        freshness_seconds=120,
        drift_score=Decimal("0.15"),
        as_of="2026-01-01",
    )
    port = InMemoryDataQualityPort(reports={"trades": custom})
    result = await port.get_quality_report("trades")
    assert result is custom


async def test_list_datasets_reflects_signals_keys() -> None:
    """list_datasets returns the keys from the injected signals dict."""
    signals = {
        "ds_alpha": DriftSignal(
            dataset="ds_alpha", drift_score=Decimal("0.01"), as_of="2026-01-01"
        ),
        "ds_beta": DriftSignal(dataset="ds_beta", drift_score=Decimal("0.02"), as_of="2026-01-01"),
    }
    port = InMemoryDataQualityPort(signals=signals)
    result = await port.list_datasets()
    assert set(result) == {"ds_alpha", "ds_beta"}


async def test_list_datasets_returns_defensive_copy() -> None:
    """list_datasets returns a new list each time — mutations don't affect the port."""
    port = InMemoryDataQualityPort()
    r1 = await port.list_datasets()
    r2 = await port.list_datasets()
    assert r1 == r2
    r1.clear()
    r3 = await port.list_datasets()
    assert len(r3) > 0


async def test_get_freshness_returns_value_from_report_seed() -> None:
    """get_freshness reads freshness_seconds from the corresponding report seed."""
    report = DataQualityReport(
        dataset="trades",
        null_rate=Decimal("0.00"),
        schema_conformance=Decimal("1.00"),
        freshness_seconds=999,
        drift_score=Decimal("0.00"),
        as_of="2026-01-01",
    )
    port = InMemoryDataQualityPort(reports={"trades": report})
    result = await port.get_freshness("trades")
    assert result == 999


# ---------------------------------------------------------------------------
# Failure paths — fail_on_call=True
# ---------------------------------------------------------------------------


async def test_fail_on_get_drift_score() -> None:
    """fail_on_call=True raises DataQualityPortError on get_drift_score."""
    port = InMemoryDataQualityPort(fail_on_call=True)
    with pytest.raises(DataQualityPortError):
        await port.get_drift_score("payments")


async def test_fail_on_get_quality_report() -> None:
    """fail_on_call=True raises DataQualityPortError on get_quality_report."""
    port = InMemoryDataQualityPort(fail_on_call=True)
    with pytest.raises(DataQualityPortError):
        await port.get_quality_report("payments")


async def test_fail_on_list_datasets() -> None:
    """fail_on_call=True raises DataQualityPortError on list_datasets."""
    port = InMemoryDataQualityPort(fail_on_call=True)
    with pytest.raises(DataQualityPortError):
        await port.list_datasets()


async def test_fail_on_get_freshness() -> None:
    """fail_on_call=True raises DataQualityPortError on get_freshness."""
    port = InMemoryDataQualityPort(fail_on_call=True)
    with pytest.raises(DataQualityPortError):
        await port.get_freshness("payments")


# ---------------------------------------------------------------------------
# Unknown dataset paths
# ---------------------------------------------------------------------------


async def test_unknown_dataset_get_drift_score_raises() -> None:
    """Unknown dataset raises DataQualityPortError on get_drift_score."""
    port = InMemoryDataQualityPort()
    with pytest.raises(DataQualityPortError):
        await port.get_drift_score("no_such_dataset")


async def test_unknown_dataset_get_quality_report_raises() -> None:
    """Unknown dataset raises DataQualityPortError on get_quality_report."""
    port = InMemoryDataQualityPort()
    with pytest.raises(DataQualityPortError):
        await port.get_quality_report("no_such_dataset")


async def test_unknown_dataset_get_freshness_raises() -> None:
    """Unknown dataset raises DataQualityPortError on get_freshness."""
    port = InMemoryDataQualityPort()
    with pytest.raises(DataQualityPortError):
        await port.get_freshness("no_such_dataset")


# ---------------------------------------------------------------------------
# Value type invariants (frozen=True, I-01 Decimal)
# ---------------------------------------------------------------------------


def test_drift_signal_is_frozen() -> None:
    """DriftSignal is a frozen dataclass — mutation raises FrozenInstanceError."""
    signal = DriftSignal(dataset="x", drift_score=Decimal("0.1"), as_of="2026-01-01")
    with pytest.raises(dataclasses.FrozenInstanceError):
        signal.drift_score = Decimal("0.9")  # type: ignore[misc]


def test_data_quality_report_is_frozen() -> None:
    """DataQualityReport is a frozen dataclass — mutation raises FrozenInstanceError."""
    report = DataQualityReport(
        dataset="x",
        null_rate=Decimal("0.01"),
        schema_conformance=Decimal("0.99"),
        freshness_seconds=60,
        drift_score=Decimal("0.05"),
        as_of="2026-01-01",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.null_rate = Decimal("0.99")  # type: ignore[misc]


def test_drift_signal_drift_score_is_decimal_not_float() -> None:
    """I-01: drift_score must be Decimal — float would violate the invariant."""
    signal = DriftSignal(dataset="x", drift_score=Decimal("0.05"), as_of="2026-01-01")
    assert isinstance(signal.drift_score, Decimal)
    assert not isinstance(signal.drift_score, float)


def test_data_quality_report_numeric_fields_are_decimal() -> None:
    """I-01: null_rate, schema_conformance, drift_score must all be Decimal."""
    report = DataQualityReport(
        dataset="y",
        null_rate=Decimal("0.02"),
        schema_conformance=Decimal("0.98"),
        freshness_seconds=100,
        drift_score=Decimal("0.10"),
        as_of="2026-01-01",
    )
    assert isinstance(report.null_rate, Decimal)
    assert isinstance(report.schema_conformance, Decimal)
    assert isinstance(report.drift_score, Decimal)
    assert isinstance(report.freshness_seconds, int)


# ---------------------------------------------------------------------------
# Port is abstract
# ---------------------------------------------------------------------------


def test_data_quality_port_cannot_be_instantiated() -> None:
    """DataQualityPort is abstract — direct instantiation raises TypeError."""
    with pytest.raises(TypeError):
        DataQualityPort()  # type: ignore[abstract]
