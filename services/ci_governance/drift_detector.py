"""
drift_detector.py — Compare live GitHub branch-protection state against
the S16.5 baseline JSON, return a structured DriftResult (S16.6).

Pure comparison logic. The only side effects are:
  - reader.read_main_protection() (delegated to the Port; the InMemory
    adapter is fully offline)
  - reading the baseline JSON file from disk

No alerting; no logging beyond what the caller chooses to do with the
returned DriftResult. DriftAlertEmitter handles routing.

Severity intent:
  - Context-set drift (missing OR extra) and enforce_admins toggle change → MAJOR
  - `strict` toggle change from true → false (protection weakened) → CRITICAL
The DriftResult exposes both `strict_differs` and `strict_weakened` so
the emitter can pick the right severity without re-reading the payload.

Baseline shape (per S16.5 .github/protection-update-v2.json):
  {
    "required_status_checks": {"strict": bool, "checks": [{"context": str}, ...]},
    "enforce_admins": bool,
    ...
  }

Live shape (per GitHub REST API):
  {
    "required_status_checks": {"strict": bool, "checks": [{"context": str, ...}, ...]},
    "enforce_admins": {"enabled": bool, ...},
    ...
  }
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import json
from pathlib import Path
import time


@dataclass(frozen=True)
class DriftResult:
    """Outcome of one drift comparison."""

    drift_detected: bool
    missing_contexts: list[str] = field(default_factory=list)
    extra_contexts: list[str] = field(default_factory=list)
    strict_differs: bool = False
    strict_weakened: bool = False
    enforce_admins_differs: bool = False
    baseline_path: str = ""
    checked_at: float = 0.0
    summary: str = ""


def _contexts(state: dict) -> list[str]:
    rsc = state.get("required_status_checks") or {}
    return [c.get("context", "") for c in (rsc.get("checks") or []) if c.get("context")]


def _strict(state: dict) -> bool | None:
    rsc = state.get("required_status_checks") or {}
    val = rsc.get("strict")
    if isinstance(val, bool):
        return val
    return None


def _enforce_admins(state: dict) -> bool | None:
    val = state.get("enforce_admins")
    if isinstance(val, bool):
        return val
    if isinstance(val, dict):
        inner = val.get("enabled")
        if isinstance(inner, bool):
            return inner
    return None


class DriftDetector:
    """Compare live protection state against a baseline JSON file."""

    def __init__(
        self,
        reader,
        baseline_path: str = ".github/protection-update-v2.json",
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._reader = reader
        self._baseline_path = baseline_path
        self._clock = clock

    def detect_drift(self) -> DriftResult:
        baseline_file = Path(self._baseline_path)
        if not baseline_file.is_file():
            raise FileNotFoundError(f"baseline JSON not found: {self._baseline_path}")
        baseline = json.loads(baseline_file.read_text(encoding="utf-8"))
        live = self._reader.read_main_protection()

        baseline_ctx = set(_contexts(baseline))
        live_ctx = set(_contexts(live))
        missing = sorted(baseline_ctx - live_ctx)
        extra = sorted(live_ctx - baseline_ctx)

        b_strict = _strict(baseline)
        l_strict = _strict(live)
        strict_differs = b_strict != l_strict
        # "strict_weakened" = baseline expected strict=true, live has strict=false
        strict_weakened = b_strict is True and l_strict is False

        b_admins = _enforce_admins(baseline)
        l_admins = _enforce_admins(live)
        admins_differs = b_admins != l_admins

        drift = bool(missing or extra or strict_differs or admins_differs)
        summary_parts: list[str] = []
        if missing:
            summary_parts.append(f"missing_contexts={missing}")
        if extra:
            summary_parts.append(f"extra_contexts={extra}")
        if strict_differs:
            summary_parts.append(f"strict_differs(baseline={b_strict},live={l_strict})")
        if admins_differs:
            summary_parts.append(f"enforce_admins_differs(baseline={b_admins},live={l_admins})")
        summary = "; ".join(summary_parts) if summary_parts else "no drift"

        return DriftResult(
            drift_detected=drift,
            missing_contexts=missing,
            extra_contexts=extra,
            strict_differs=strict_differs,
            strict_weakened=strict_weakened,
            enforce_admins_differs=admins_differs,
            baseline_path=self._baseline_path,
            checked_at=self._clock(),
            summary=summary,
        )
