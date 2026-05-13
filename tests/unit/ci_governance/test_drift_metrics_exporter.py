"""
Tests for services/ci_governance/drift_metrics_exporter.py — S16.11.

All tests are deterministic: FakeHistoryStore with canned entries, fixed clock.
No network, no mutation, no side effects beyond tmp_path writes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from services.ci_governance.drift_metrics_exporter import (
    DriftMetricsExporter,
)

# ---------------------------------------------------------------------------
# FakeHistoryStore — deterministic substitute for DriftHistoryStore
# ---------------------------------------------------------------------------


class FakeHistoryStore:
    """In-memory history store for test isolation."""

    def __init__(self, entries: list[dict]) -> None:
        self._entries = list(entries)

    def read_all(self, limit: int | None = None) -> list[dict]:
        if limit is not None:
            return self._entries[:limit]
        return list(self._entries)

    def read_since(self, since_ts: float) -> list[dict]:
        return [e for e in self._entries if e.get("ts", 0) >= since_ts]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FIXED_CLOCK = 100_000.0

_ENTRIES: list[dict] = [
    {
        "ts": 90_000.0,
        "drift_detected": False,
        "strict_weakened": False,
        "missing_rules": [],
        "extra_rules": [],
        "summary": "no drift",
    },
    {
        "ts": 95_000.0,
        "drift_detected": True,
        "strict_weakened": False,
        "missing_rules": ["r1"],
        "extra_rules": [],
        "summary": "drift found",
    },
    {
        "ts": 98_000.0,
        "drift_detected": True,
        "strict_weakened": True,
        "missing_rules": ["r1", "r2"],
        "extra_rules": ["x1"],
        "summary": "critical drift",
    },
    {
        "ts": 99_000.0,
        "drift_detected": False,
        "strict_weakened": False,
        "missing_rules": [],
        "extra_rules": ["x2"],
        "summary": "resolved",
    },
]


@pytest.fixture()
def store() -> FakeHistoryStore:
    return FakeHistoryStore(_ENTRIES)


@pytest.fixture()
def exporter(store: FakeHistoryStore) -> DriftMetricsExporter:
    return DriftMetricsExporter(
        history_store=store,
        clock=lambda: _FIXED_CLOCK,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_export_writes_textfile_at_target_path(
    exporter: DriftMetricsExporter,
    tmp_path: Path,
) -> None:
    target = tmp_path / "metrics.prom"
    result = exporter.export(str(target))
    assert result.success is True
    assert target.is_file()
    assert result.textfile_path == str(target)


def test_export_uses_atomic_tmpfile_then_rename(
    store: FakeHistoryStore,
    tmp_path: Path,
) -> None:
    """Verify custom file_writer is called (proves injection slot works)."""
    calls: list[tuple[str, str]] = []

    def tracking_writer(path: str, body: str) -> None:
        calls.append((path, body))

    exp = DriftMetricsExporter(
        history_store=store,
        clock=lambda: _FIXED_CLOCK,
        file_writer=tracking_writer,
    )
    target = str(tmp_path / "metrics.prom")
    result = exp.export(target)
    assert result.success is True
    assert len(calls) == 1
    assert calls[0][0] == target


def test_export_emits_all_metric_help_and_type_lines(
    exporter: DriftMetricsExporter,
    tmp_path: Path,
) -> None:
    target = tmp_path / "metrics.prom"
    exporter.export(str(target))
    content = target.read_text(encoding="utf-8")

    expected_metrics = [
        "banxe_ci_drift_events_total",
        "banxe_ci_drift_detected_total",
        "banxe_ci_drift_strict_weakened_total",
        "banxe_ci_drift_missing_contexts_last_count",
        "banxe_ci_drift_extra_contexts_last_count",
        "banxe_ci_drift_last_check_timestamp_seconds",
        "banxe_ci_drift_exporter_last_export_timestamp_seconds",
    ]
    for metric in expected_metrics:
        assert f"# HELP {metric}" in content
        assert f"# TYPE {metric}" in content


def test_export_counts_drift_detected_correctly(
    exporter: DriftMetricsExporter,
    tmp_path: Path,
) -> None:
    target = tmp_path / "metrics.prom"
    exporter.export(str(target), window_seconds=86400)
    content = target.read_text(encoding="utf-8")
    # 2 entries have drift_detected=True (ts=95000, ts=98000)
    assert 'banxe_ci_drift_detected_total{window_seconds="86400"} 2' in content


def test_export_counts_strict_weakened_correctly(
    exporter: DriftMetricsExporter,
    tmp_path: Path,
) -> None:
    target = tmp_path / "metrics.prom"
    exporter.export(str(target), window_seconds=86400)
    content = target.read_text(encoding="utf-8")
    # 1 entry has strict_weakened=True (ts=98000)
    assert 'banxe_ci_drift_strict_weakened_total{window_seconds="86400"} 1' in content


def test_export_uses_window_seconds_to_filter_history(
    exporter: DriftMetricsExporter,
    tmp_path: Path,
) -> None:
    target = tmp_path / "metrics.prom"
    # window=5000 → since_ts = 100000 - 5000 = 95000 → entries at 95k, 98k, 99k
    exporter.export(str(target), window_seconds=5000)
    content = target.read_text(encoding="utf-8")
    assert 'banxe_ci_drift_events_total{window_seconds="5000"} 3' in content


def test_export_emits_zero_metrics_when_history_empty(
    tmp_path: Path,
) -> None:
    empty_store = FakeHistoryStore([])
    exp = DriftMetricsExporter(
        history_store=empty_store,
        clock=lambda: _FIXED_CLOCK,
    )
    target = tmp_path / "metrics.prom"
    result = exp.export(str(target))
    assert result.success is True
    assert result.entries_scanned == 0
    content = target.read_text(encoding="utf-8")
    assert 'banxe_ci_drift_events_total{window_seconds="86400"} 0' in content
    assert "banxe_ci_drift_last_check_timestamp_seconds 0.0" in content


def test_export_emits_last_check_timestamp_from_latest_entry(
    exporter: DriftMetricsExporter,
    tmp_path: Path,
) -> None:
    target = tmp_path / "metrics.prom"
    exporter.export(str(target), window_seconds=86400)
    content = target.read_text(encoding="utf-8")
    # Latest entry ts = 99000.0
    assert "banxe_ci_drift_last_check_timestamp_seconds 99000.0" in content


def test_export_includes_exporter_last_export_timestamp_from_clock(
    exporter: DriftMetricsExporter,
    tmp_path: Path,
) -> None:
    target = tmp_path / "metrics.prom"
    exporter.export(str(target))
    content = target.read_text(encoding="utf-8")
    assert f"banxe_ci_drift_exporter_last_export_timestamp_seconds {_FIXED_CLOCK}" in content


def test_export_returns_failure_when_write_raises_clear_error(
    store: FakeHistoryStore,
) -> None:
    def failing_writer(path: str, body: str) -> None:
        raise OSError("disk full")

    exp = DriftMetricsExporter(
        history_store=store,
        clock=lambda: _FIXED_CLOCK,
        file_writer=failing_writer,
    )
    result = exp.export("/nonexistent/metrics.prom")
    assert result.success is False
    assert result.error is not None
    assert "disk full" in result.error
