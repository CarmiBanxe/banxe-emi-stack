"""Unit tests for ProtectionSnapshotWriter (S16.8)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from services.ci_governance.snapshot_writer import (
    ProtectionSnapshotWriter,
    SnapshotResult,
)


class _FakeReader:
    """In-memory GitHubProtectionReaderPort double + mutation-call ledger."""

    _ALL_METHODS = ("read_main_protection",)

    def __init__(self, payload: dict, raise_exc: Exception | None = None) -> None:
        self._payload = payload
        self._raise = raise_exc
        self.calls: list[str] = []

    def read_main_protection(self) -> dict:
        self.calls.append("read_main_protection")
        if self._raise is not None:
            raise self._raise
        return dict(self._payload)


_CANONICAL_PAYLOAD: dict[str, Any] = {
    "required_status_checks": {
        "strict": True,
        "checks": [
            {"context": "Smoke Gate (mock tier)"},
            {"context": "guardian-factory"},
        ],
    },
    "enforce_admins": {"enabled": False},
}


def test_capture_writes_payload_as_json_to_target_path(tmp_path: Path) -> None:
    target = tmp_path / "snap.json"
    writer = ProtectionSnapshotWriter(
        reader=_FakeReader(_CANONICAL_PAYLOAD),
        clock=lambda: 1715000000.0,
    )
    result = writer.capture(str(target))
    assert result.success is True
    assert target.is_file()
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written == _CANONICAL_PAYLOAD


def test_capture_uses_atomic_tmpfile_then_rename(tmp_path: Path) -> None:
    """The default file_writer must write through a sibling tmpfile and
    atomically rename. After capture: target exists, no leftover tmpfiles
    in the parent directory."""
    target = tmp_path / "snap.json"
    writer = ProtectionSnapshotWriter(
        reader=_FakeReader(_CANONICAL_PAYLOAD),
        clock=lambda: 1715000000.0,
    )
    result = writer.capture(str(target))
    assert result.success is True
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith("snap.json.tmp.")]
    assert leftovers == [], f"tmpfile leftovers after rename: {leftovers}"
    assert target.is_file()


def test_capture_serialises_with_sorted_keys(tmp_path: Path) -> None:
    target = tmp_path / "snap.json"
    payload = {"b": 2, "a": 1, "c": {"y": 1, "x": 0}}
    writer = ProtectionSnapshotWriter(
        reader=_FakeReader(payload),
        clock=lambda: 1715000000.0,
    )
    writer.capture(str(target))
    raw = target.read_text(encoding="utf-8")
    # First key in raw output must be 'a' (sorted alphabetically).
    first_a = raw.find('"a"')
    first_b = raw.find('"b"')
    first_c = raw.find('"c"')
    assert -1 < first_a < first_b < first_c
    # Nested objects sorted too.
    nested_x = raw.find('"x"')
    nested_y = raw.find('"y"')
    assert -1 < nested_x < nested_y


def test_capture_appends_trailing_newline(tmp_path: Path) -> None:
    target = tmp_path / "snap.json"
    writer = ProtectionSnapshotWriter(
        reader=_FakeReader(_CANONICAL_PAYLOAD),
        clock=lambda: 1715000000.0,
    )
    writer.capture(str(target))
    body = target.read_text(encoding="utf-8")
    assert body.endswith("\n"), "snapshot must end with a trailing newline"


def test_capture_returns_byte_size_in_result(tmp_path: Path) -> None:
    target = tmp_path / "snap.json"
    writer = ProtectionSnapshotWriter(
        reader=_FakeReader(_CANONICAL_PAYLOAD),
        clock=lambda: 1715000000.0,
    )
    result = writer.capture(str(target))
    assert isinstance(result.byte_size, int)
    assert result.byte_size > 0
    assert result.byte_size == os.path.getsize(target)


def test_capture_uses_injected_clock_for_captured_at(tmp_path: Path) -> None:
    fixed = 1715111111.0
    writer = ProtectionSnapshotWriter(
        reader=_FakeReader(_CANONICAL_PAYLOAD),
        clock=lambda: fixed,
    )
    result = writer.capture(str(tmp_path / "snap.json"))
    assert result.captured_at == fixed


def test_capture_returns_failure_when_reader_raises(tmp_path: Path) -> None:
    target = tmp_path / "snap.json"
    writer = ProtectionSnapshotWriter(
        reader=_FakeReader({}, raise_exc=RuntimeError("HTTP 401 from GitHub")),
        clock=lambda: 1715000000.0,
    )
    result: SnapshotResult = writer.capture(str(target))
    assert result.success is False
    assert result.byte_size is None
    assert "reader" in (result.error or "")
    assert "RuntimeError" in (result.error or "")
    assert not target.exists(), "target file must NOT be written when reader fails"


def test_capture_never_calls_mutation_methods_on_reader(tmp_path: Path) -> None:
    target = tmp_path / "snap.json"
    reader = _FakeReader(_CANONICAL_PAYLOAD)
    writer = ProtectionSnapshotWriter(reader=reader, clock=lambda: 1715000000.0)
    for _ in range(3):
        writer.capture(str(target))
    # Only read_main_protection ever called.
    assert set(reader.calls) == {"read_main_protection"}
    # Defence-in-depth: source-text scan for forbidden mutation literals.
    src = Path(
        Path(__file__).resolve().parents[3] / "services" / "ci_governance" / "snapshot_writer.py"
    ).read_text(encoding="utf-8")
    for forbidden in ("PUT", "PATCH", "DELETE", "POST"):
        for needle in (f'"{forbidden}"', f"'{forbidden}'"):
            assert needle not in src, (
                f"forbidden mutation method literal {needle!r} found in snapshot_writer.py"
            )
