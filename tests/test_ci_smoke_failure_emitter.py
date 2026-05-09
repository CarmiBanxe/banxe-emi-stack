"""tests/test_ci_smoke_failure_emitter.py — ADR-035 Step 5 unit tests.

Covers scripts/emit-ci-smoke-failure.py: event construction, routing logic,
and resilience (always exits 0).
"""

from __future__ import annotations

from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

import pytest

# Ensure repo root is importable (mirrors how the script bootstraps itself)
REPO_ROOT = str(Path(__file__).parent.parent)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import scripts.emit_ci_smoke_failure as emitter  # type: ignore[import]

# ── build_event() ─────────────────────────────────────────────────────────────


def test_build_event_type() -> None:
    event = emitter.build_event()
    assert event.event_type == "CI_SMOKE_FAILURE"


def test_build_event_severity_critical() -> None:
    event = emitter.build_event()
    assert event.severity == "CRITICAL"


def test_build_event_actor_contains_smoke_gate() -> None:
    event = emitter.build_event()
    assert "smoke-gate-full" in event.actor


def test_build_event_entity_id_contains_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_RUN_ID", "99887766")
    event = emitter.build_event()
    assert "99887766" in event.entity_id


def test_build_event_payload_workflow_name() -> None:
    event = emitter.build_event()
    assert event.payload["workflow"] == "smoke-gate-full.yml"


def test_build_event_payload_run_id_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_RUN_ID", "12345678")
    event = emitter.build_event()
    assert event.payload["run_id"] == "12345678"


def test_build_event_payload_tier_is_full() -> None:
    event = emitter.build_event()
    assert event.payload["tier"] == "full"


def test_build_event_payload_run_url_contains_github(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_RUN_ID", "55544433")
    monkeypatch.setenv("GITHUB_REPOSITORY", "CarmiBanxe/banxe-emi-stack")
    event = emitter.build_event()
    assert "github.com" in event.payload["run_url"]
    assert "55544433" in event.payload["run_url"]


def test_build_event_payload_occurred_at_is_iso() -> None:
    import re

    event = emitter.build_event()
    iso_pattern = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    assert re.match(iso_pattern, event.payload["occurred_at"])


def test_build_event_has_unique_event_id() -> None:
    e1 = emitter.build_event()
    e2 = emitter.build_event()
    assert e1.event_id != e2.event_id


# ── emit() routing logic ───────────────────────────────────────────────────────


def test_emit_uses_audit_trail_when_clickhouse_host_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLICKHOUSE_HOST", "localhost")
    mock_trail = MagicMock()
    mock_trail.log.return_value = True
    with patch("scripts.emit_ci_smoke_failure.AuditTrail", return_value=mock_trail):
        emitter.emit()
    mock_trail.log.assert_called_once()


def test_emit_uses_buffered_port_when_no_clickhouse_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLICKHOUSE_HOST", raising=False)
    mock_port = MagicMock()
    with (
        patch("scripts.emit_ci_smoke_failure.AuditTrail") as mock_trail_cls,
        patch("src.safeguarding.buffered_audit_port.BufferedAuditPort", return_value=mock_port),
    ):
        emitter.emit()
    mock_trail_cls.assert_not_called()
    mock_port.record.assert_called_once()


def test_emit_falls_back_to_buffer_when_clickhouse_write_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLICKHOUSE_HOST", "localhost")
    mock_trail = MagicMock()
    mock_trail.log.return_value = False  # write failed
    mock_port = MagicMock()
    with (
        patch("scripts.emit_ci_smoke_failure.AuditTrail", return_value=mock_trail),
        patch("src.safeguarding.buffered_audit_port.BufferedAuditPort", return_value=mock_port),
    ):
        emitter.emit()
    mock_port.record.assert_called_once()


def test_emit_uses_audit_buffer_path_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("CLICKHOUSE_HOST", raising=False)
    db_path = str(tmp_path / "test-audit.db")
    monkeypatch.setenv("AUDIT_BUFFER_PATH", db_path)
    emitter.emit()
    assert Path(db_path).exists()


def test_emit_uses_clickhouse_db_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLICKHOUSE_HOST", "localhost")
    monkeypatch.setenv("CLICKHOUSE_DB", "banxe_test")
    mock_trail = MagicMock()
    mock_trail.log.return_value = True
    with patch("scripts.emit_ci_smoke_failure.AuditTrail", return_value=mock_trail) as cls:
        emitter.emit()
    _, kwargs = cls.call_args
    assert kwargs.get("database") == "banxe_test"


# ── main() resilience ─────────────────────────────────────────────────────────


def test_main_exits_zero_on_success() -> None:
    with (
        patch("scripts.emit_ci_smoke_failure.emit"),
        pytest.raises(SystemExit) as exc_info,
    ):
        emitter.main()
    assert exc_info.value.code == 0


def test_main_exits_zero_even_on_emit_exception() -> None:
    with (
        patch("scripts.emit_ci_smoke_failure.emit", side_effect=RuntimeError("boom")),
        pytest.raises(SystemExit) as exc_info,
    ):
        emitter.main()
    assert exc_info.value.code == 0
