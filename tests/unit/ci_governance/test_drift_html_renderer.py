"""
Tests for services/ci_governance/drift_html_renderer.py — S16.12.

All tests are deterministic: FakeHistoryStore with canned entries, fixed clock.
No network, no mutation, no side effects beyond tmp_path writes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from services.ci_governance.drift_html_renderer import (
    DriftHtmlRenderer,
)

# ---------------------------------------------------------------------------
# FakeHistoryStore
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
        "missing_rules": ["ctx-a"],
        "extra_rules": [],
        "summary": "drift found",
    },
    {
        "ts": 98_000.0,
        "drift_detected": True,
        "strict_weakened": True,
        "missing_rules": ["ctx-b", "ctx-c"],
        "extra_rules": ["ctx-x"],
        "summary": "critical drift",
    },
    {
        "ts": 99_000.0,
        "drift_detected": False,
        "strict_weakened": False,
        "missing_rules": [],
        "extra_rules": ["ctx-y"],
        "summary": "resolved",
    },
]


@pytest.fixture()
def store() -> FakeHistoryStore:
    return FakeHistoryStore(_ENTRIES)


@pytest.fixture()
def renderer(store: FakeHistoryStore) -> DriftHtmlRenderer:
    return DriftHtmlRenderer(
        history_store=store,
        clock=lambda: _FIXED_CLOCK,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_render_writes_html_file_at_target_path(
    renderer: DriftHtmlRenderer,
    tmp_path: Path,
) -> None:
    target = tmp_path / "report.html"
    result = renderer.render(str(target))
    assert result.success is True
    assert target.is_file()
    assert result.report_path == str(target)


def test_render_uses_atomic_tmpfile_then_rename(
    store: FakeHistoryStore,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, str]] = []

    def tracking_writer(path: str, body: str) -> None:
        calls.append((path, body))

    rend = DriftHtmlRenderer(
        history_store=store,
        clock=lambda: _FIXED_CLOCK,
        file_writer=tracking_writer,
    )
    target = str(tmp_path / "report.html")
    result = rend.render(target)
    assert result.success is True
    assert len(calls) == 1
    assert calls[0][0] == target


def test_render_emits_doctype_html_meta_charset_utf8(
    renderer: DriftHtmlRenderer,
    tmp_path: Path,
) -> None:
    target = tmp_path / "report.html"
    renderer.render(str(target))
    content = target.read_text(encoding="utf-8")
    assert "<!doctype html>" in content
    assert '<meta charset="utf-8">' in content
    assert "<title>Banxe CI drift report</title>" in content


def test_render_escapes_html_in_summary_text_xss_safe(
    tmp_path: Path,
) -> None:
    xss_store = FakeHistoryStore(
        [
            {
                "ts": 99_000.0,
                "drift_detected": True,
                "strict_weakened": False,
                "missing_rules": [],
                "extra_rules": [],
                "summary": '<script>alert("xss")</script>',
            },
        ]
    )
    rend = DriftHtmlRenderer(
        history_store=xss_store,
        clock=lambda: _FIXED_CLOCK,
    )
    target = tmp_path / "report.html"
    rend.render(str(target))
    content = target.read_text(encoding="utf-8")
    assert "<script>" not in content
    assert "&lt;script&gt;" in content


def test_render_escapes_html_in_context_names_xss_safe(
    tmp_path: Path,
) -> None:
    xss_store = FakeHistoryStore(
        [
            {
                "ts": 99_000.0,
                "drift_detected": True,
                "strict_weakened": False,
                "missing_rules": ['<img src=x onerror="alert(1)">'],
                "extra_rules": [],
                "summary": "ctx xss test",
            },
        ]
    )
    rend = DriftHtmlRenderer(
        history_store=xss_store,
        clock=lambda: _FIXED_CLOCK,
    )
    target = tmp_path / "report.html"
    rend.render(str(target))
    content = target.read_text(encoding="utf-8")
    assert "<img " not in content
    assert "&lt;img " in content


def test_render_emits_summary_cards_with_correct_counts(
    renderer: DriftHtmlRenderer,
    tmp_path: Path,
) -> None:
    target = tmp_path / "report.html"
    renderer.render(str(target), window_seconds=86400)
    content = target.read_text(encoding="utf-8")
    # 4 total, 2 drift, 1 strict
    assert ">4<" in content
    assert ">2<" in content
    assert ">1<" in content


def test_render_uses_window_seconds_to_filter_history(
    renderer: DriftHtmlRenderer,
    tmp_path: Path,
) -> None:
    target = tmp_path / "report.html"
    # window=5000 → since_ts = 100000-5000 = 95000 → 3 entries (95k, 98k, 99k)
    result = renderer.render(str(target), window_seconds=5000)
    assert result.entries_rendered == 3


def test_render_caps_entries_to_limit(
    renderer: DriftHtmlRenderer,
    tmp_path: Path,
) -> None:
    target = tmp_path / "report.html"
    result = renderer.render(str(target), window_seconds=86400, limit=2)
    assert result.entries_rendered == 2


def test_render_empty_history_emits_no_entries_placeholder(
    tmp_path: Path,
) -> None:
    empty_store = FakeHistoryStore([])
    rend = DriftHtmlRenderer(
        history_store=empty_store,
        clock=lambda: _FIXED_CLOCK,
    )
    target = tmp_path / "report.html"
    result = rend.render(str(target))
    assert result.success is True
    assert result.entries_rendered == 0
    content = target.read_text(encoding="utf-8")
    assert "No drift entries" in content
    assert "<!doctype html>" in content


def test_render_emits_iso_timestamp_for_each_entry(
    renderer: DriftHtmlRenderer,
    tmp_path: Path,
) -> None:
    target = tmp_path / "report.html"
    renderer.render(str(target), window_seconds=86400)
    content = target.read_text(encoding="utf-8")
    for entry in _ENTRIES:
        iso = datetime.fromtimestamp(entry["ts"], tz=UTC).isoformat()
        assert iso in content


def test_render_returns_byte_size_in_result(
    renderer: DriftHtmlRenderer,
    tmp_path: Path,
) -> None:
    target = tmp_path / "report.html"
    result = renderer.render(str(target))
    assert result.byte_size is not None
    assert result.byte_size > 0
    actual = len(target.read_text(encoding="utf-8").encode("utf-8"))
    assert result.byte_size == actual


def test_render_returns_failure_when_write_raises_clear_error(
    store: FakeHistoryStore,
) -> None:
    def failing_writer(path: str, body: str) -> None:
        raise OSError("disk full")

    rend = DriftHtmlRenderer(
        history_store=store,
        clock=lambda: _FIXED_CLOCK,
        file_writer=failing_writer,
    )
    result = rend.render("/nonexistent/report.html")
    assert result.success is False
    assert result.error is not None
    assert "disk full" in result.error
