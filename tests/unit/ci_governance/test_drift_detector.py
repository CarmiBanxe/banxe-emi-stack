"""Unit tests for DriftDetector (S16.6)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.ci_governance.drift_detector import DriftDetector
from services.ci_governance.factory import get_drift_detector
from services.ci_governance.in_memory_protection_reader import InMemoryProtectionReader

_CANONICAL_BASELINE = {
    "required_status_checks": {
        "strict": True,
        "checks": [
            {"context": "guardian-factory"},
            {"context": "guardian-project"},
            {"context": "Smoke Gate (mock tier)"},
            {"context": "Pytest (coverage >= 80%)"},
        ],
    },
    "enforce_admins": False,
    "required_pull_request_reviews": None,
    "restrictions": None,
}


def _live_matching() -> dict:
    # GitHub API shape — enforce_admins comes back as an object with `enabled`.
    return {
        "required_status_checks": {
            "strict": True,
            "checks": [
                {"context": "guardian-factory", "app_id": 15368},
                {"context": "guardian-project", "app_id": 15368},
                {"context": "Smoke Gate (mock tier)", "app_id": 15368},
                {"context": "Pytest (coverage >= 80%)", "app_id": 15368},
            ],
        },
        "enforce_admins": {"enabled": False},
    }


def _write_baseline(tmp_path: Path, payload: dict | None = None) -> Path:
    path = tmp_path / "protection-update-v2.json"
    path.write_text(json.dumps(payload or _CANONICAL_BASELINE), encoding="utf-8")
    return path


def _make_detector(
    tmp_path: Path,
    live_payload: dict | None = None,
    baseline_payload: dict | None = None,
    clock_value: float = 1714000000.0,
) -> DriftDetector:
    baseline_path = _write_baseline(tmp_path, baseline_payload)
    reader = InMemoryProtectionReader(live_payload or _live_matching())
    return DriftDetector(
        reader=reader,
        baseline_path=str(baseline_path),
        clock=lambda: clock_value,
    )


def test_drift_detector_clean_when_live_matches_baseline(tmp_path: Path) -> None:
    detector = _make_detector(tmp_path)
    result = detector.detect_drift()
    assert result.drift_detected is False
    assert result.missing_contexts == []
    assert result.extra_contexts == []
    assert result.strict_differs is False
    assert result.strict_weakened is False
    assert result.enforce_admins_differs is False
    assert result.summary == "no drift"


def test_drift_detector_detects_missing_context_in_live(tmp_path: Path) -> None:
    live = _live_matching()
    live["required_status_checks"]["checks"] = [
        c
        for c in live["required_status_checks"]["checks"]
        if c["context"] != "Pytest (coverage >= 80%)"
    ]
    detector = _make_detector(tmp_path, live_payload=live)
    result = detector.detect_drift()
    assert result.drift_detected is True
    assert "Pytest (coverage >= 80%)" in result.missing_contexts
    assert result.extra_contexts == []


def test_drift_detector_detects_extra_context_in_live(tmp_path: Path) -> None:
    live = _live_matching()
    live["required_status_checks"]["checks"].append(
        {"context": "Unsanctioned Check", "app_id": 99999}
    )
    detector = _make_detector(tmp_path, live_payload=live)
    result = detector.detect_drift()
    assert result.drift_detected is True
    assert result.missing_contexts == []
    assert "Unsanctioned Check" in result.extra_contexts


def test_drift_detector_detects_strict_toggle_change_critical(tmp_path: Path) -> None:
    live = _live_matching()
    live["required_status_checks"]["strict"] = False  # protection weakened
    detector = _make_detector(tmp_path, live_payload=live)
    result = detector.detect_drift()
    assert result.drift_detected is True
    assert result.strict_differs is True
    assert result.strict_weakened is True  # baseline True → live False


def test_drift_detector_detects_enforce_admins_toggle_change(tmp_path: Path) -> None:
    live = _live_matching()
    live["enforce_admins"] = {"enabled": True}  # baseline is False
    detector = _make_detector(tmp_path, live_payload=live)
    result = detector.detect_drift()
    assert result.drift_detected is True
    assert result.enforce_admins_differs is True


def test_drift_detector_uses_injected_clock_for_checked_at(tmp_path: Path) -> None:
    detector = _make_detector(tmp_path, clock_value=1714000000.0)
    result = detector.detect_drift()
    assert result.checked_at == 1714000000.0


def test_drift_detector_summary_lists_all_diffs(tmp_path: Path) -> None:
    live = _live_matching()
    live["required_status_checks"]["strict"] = False
    live["required_status_checks"]["checks"] = [
        c for c in live["required_status_checks"]["checks"] if c["context"] != "guardian-project"
    ]
    live["required_status_checks"]["checks"].append({"context": "Phantom"})
    live["enforce_admins"] = {"enabled": True}
    detector = _make_detector(tmp_path, live_payload=live)
    result = detector.detect_drift()
    assert result.drift_detected is True
    assert "missing_contexts" in result.summary
    assert "extra_contexts" in result.summary
    assert "strict_differs" in result.summary
    assert "enforce_admins_differs" in result.summary


def test_drift_detector_baseline_file_missing_raises_clear_error(
    tmp_path: Path,
) -> None:
    reader = InMemoryProtectionReader(_live_matching())
    detector = DriftDetector(
        reader=reader,
        baseline_path=str(tmp_path / "does-not-exist.json"),
    )
    with pytest.raises(FileNotFoundError, match="baseline JSON not found"):
        detector.detect_drift()


def test_drift_detector_live_payload_missing_required_status_checks_returns_drift_with_summary(
    tmp_path: Path,
) -> None:
    live = {"enforce_admins": {"enabled": False}}  # no required_status_checks at all
    detector = _make_detector(tmp_path, live_payload=live)
    result = detector.detect_drift()
    assert result.drift_detected is True
    # All baseline contexts are missing from the live payload.
    assert set(result.missing_contexts) == {
        "guardian-factory",
        "guardian-project",
        "Smoke Gate (mock tier)",
        "Pytest (coverage >= 80%)",
    }
    assert result.strict_differs is True  # baseline True vs live (None / missing)
    # strict_weakened only fires when live is explicitly False, not None.
    assert result.strict_weakened is False


def test_factory_get_drift_detector_returns_singleton() -> None:
    get_drift_detector.cache_clear()
    try:
        a = get_drift_detector()
        b = get_drift_detector()
        assert a is b
        assert isinstance(a, DriftDetector)
    finally:
        get_drift_detector.cache_clear()
