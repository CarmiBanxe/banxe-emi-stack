"""Tests for services.ci_governance.drift_history_store (S16.9)."""

from __future__ import annotations

import fcntl
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.ci_governance.drift_detector import DriftResult
from services.ci_governance.drift_history_store import AppendResult, DriftHistoryStore


def _make_result(**overrides) -> DriftResult:
    defaults = dict(
        drift_detected=True,
        missing_contexts=["ci/lint"],
        extra_contexts=["ci/extra"],
        strict_differs=True,
        strict_weakened=False,
        enforce_admins_differs=True,
        baseline_path=".github/protection-update-v2.json",
        checked_at=1000.0,
        summary="missing_contexts=['ci/lint']",
    )
    defaults.update(overrides)
    return DriftResult(**defaults)


class TestAppend:
    def test_append_writes_single_jsonl_line_per_call(self, tmp_path: Path) -> None:
        history = tmp_path / "h.jsonl"
        store = DriftHistoryStore(str(history), clock=lambda: 1.0)
        store.append_result(_make_result())
        store.append_result(_make_result(drift_detected=False))
        lines = history.read_text().splitlines()
        assert len(lines) == 2

    def test_append_returns_success_with_byte_count(self, tmp_path: Path) -> None:
        history = tmp_path / "h.jsonl"
        store = DriftHistoryStore(str(history), clock=lambda: 2.0)
        res = store.append_result(_make_result())
        assert isinstance(res, AppendResult)
        assert res.success is True
        assert res.bytes_written is not None
        assert res.bytes_written > 0

    def test_append_serialises_all_DriftResult_fields(self, tmp_path: Path) -> None:
        history = tmp_path / "h.jsonl"
        store = DriftHistoryStore(str(history), clock=lambda: 3.0)
        result = _make_result()
        store.append_result(result)
        record = json.loads(history.read_text().strip())
        assert record["drift_detected"] is True
        assert record["missing_contexts"] == ["ci/lint"]
        assert record["extra_contexts"] == ["ci/extra"]
        assert record["strict_differs"] is True
        assert record["strict_weakened"] is False
        assert record["enforce_admins_differs"] is True
        assert record["baseline_path"] == ".github/protection-update-v2.json"
        assert record["checked_at"] == 1000.0
        assert "summary" in record
        assert record["ts"] == 3.0

    def test_append_uses_injected_clock_for_appended_at(self, tmp_path: Path) -> None:
        history = tmp_path / "h.jsonl"
        clock = MagicMock(return_value=42.5)
        store = DriftHistoryStore(str(history), clock=clock)
        res = store.append_result(_make_result())
        assert res.appended_at == 42.5
        record = json.loads(history.read_text().strip())
        assert record["ts"] == 42.5

    def test_append_does_not_truncate_existing_history(self, tmp_path: Path) -> None:
        history = tmp_path / "h.jsonl"
        history.write_text('{"old":"entry","ts":0}\n')
        store = DriftHistoryStore(str(history), clock=lambda: 5.0)
        store.append_result(_make_result())
        lines = history.read_text().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["old"] == "entry"
        assert json.loads(lines[1])["drift_detected"] is True

    def test_append_creates_parent_directory_if_missing(self, tmp_path: Path) -> None:
        history = tmp_path / "sub" / "dir" / "h.jsonl"
        store = DriftHistoryStore(str(history), clock=lambda: 6.0)
        res = store.append_result(_make_result())
        assert res.success is True
        assert history.is_file()


class TestRead:
    def test_read_all_returns_well_formed_entries_in_order(self, tmp_path: Path) -> None:
        history = tmp_path / "h.jsonl"
        store = DriftHistoryStore(str(history), clock=MagicMock(side_effect=[1.0, 2.0, 3.0]))
        for _ in range(3):
            store.append_result(_make_result())
        entries = store.read_all()
        assert len(entries) == 3
        assert entries[0]["ts"] == 1.0
        assert entries[2]["ts"] == 3.0

    def test_read_all_skips_malformed_lines_without_raising(self, tmp_path: Path) -> None:
        history = tmp_path / "h.jsonl"
        history.write_text(
            '{"ts":1.0,"drift_detected":true}\nNOT JSON\n{"ts":2.0,"drift_detected":false}\n'
        )
        store = DriftHistoryStore(str(history), clock=lambda: 0)
        entries = store.read_all()
        assert len(entries) == 2
        assert entries[0]["ts"] == 1.0
        assert entries[1]["ts"] == 2.0

    def test_read_since_filters_by_ts_inclusive_lower_bound(self, tmp_path: Path) -> None:
        history = tmp_path / "h.jsonl"
        history.write_text(
            '{"ts":10.0,"drift_detected":true}\n'
            '{"ts":20.0,"drift_detected":false}\n'
            '{"ts":30.0,"drift_detected":true}\n'
        )
        store = DriftHistoryStore(str(history), clock=lambda: 0)
        entries = store.read_since(20.0)
        assert len(entries) == 2
        assert entries[0]["ts"] == 20.0
        assert entries[1]["ts"] == 30.0


class TestFlock:
    def test_append_uses_flock_LOCK_EX_for_cross_process_safety(self, tmp_path: Path) -> None:
        history = tmp_path / "h.jsonl"
        store = DriftHistoryStore(str(history), clock=lambda: 7.0)
        with patch("services.ci_governance.drift_history_store.fcntl") as mock_fcntl:
            mock_fcntl.LOCK_EX = fcntl.LOCK_EX
            mock_fcntl.LOCK_UN = fcntl.LOCK_UN
            mock_fcntl.flock = MagicMock()
            # Use default appender — it calls fcntl.flock
            store_patched = DriftHistoryStore(str(history), clock=lambda: 7.0)
            store_patched.append_result(_make_result())
            lock_calls = mock_fcntl.flock.call_args_list
            assert len(lock_calls) == 2
            assert lock_calls[0][0][1] == fcntl.LOCK_EX
            assert lock_calls[1][0][1] == fcntl.LOCK_UN
