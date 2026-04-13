"""services/repo_watch/maturity_evaluator.py — Repo maturity scoring.

IL-093 | banxe-emi-stack

Pure, side-effect-free function: evaluate_maturity(stats, config, weeks_stable)
→ MaturityResult(level, reasons).

Decision ladder:
  1. If repo is archived              → NOT_READY  (hard stop)
  2. If any DEV_CANDIDATE gate fails  → NOT_READY  (list all failures)
  3. If any PROD_CANDIDATE gate fails → DEV_CANDIDATE
  4. Otherwise                        → PROD_CANDIDATE
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from services.repo_watch.config import RepoWatchConfig
from services.repo_watch.github_client import RepoStats


class MaturityLevel(str, Enum):
    """Three-tier repo maturity rating."""

    NOT_READY = "NOT_READY"
    DEV_CANDIDATE = "DEV_CANDIDATE"
    PROD_CANDIDATE = "PROD_CANDIDATE"


@dataclass(frozen=True)
class MaturityResult:
    """Immutable evaluation output."""

    level: MaturityLevel
    reasons: tuple[str, ...]


def evaluate_maturity(
    stats: RepoStats,
    config: RepoWatchConfig,
    *,
    weeks_stable: int = 0,
) -> MaturityResult:
    """Compute the maturity level from repo stats and config thresholds.

    Args:
        stats: Point-in-time GitHub metrics snapshot.
        config: Frozen config containing DEV and PROD thresholds.
        weeks_stable: Number of consecutive weeks the repo has been observed
            at DEV_CANDIDATE or above.  Injected by the caller so this
            function stays pure and testable.

    Returns:
        :class:`MaturityResult` with the level and human-readable reasons.
    """
    dev_t = config.dev_candidate
    prod_t = config.prod_candidate

    # ── Hard disqualifier: archived repo ────────────────────────────────────
    if stats.is_archived:
        return MaturityResult(
            level=MaturityLevel.NOT_READY,
            reasons=("repo is archived",),
        )

    now = datetime.now(tz=UTC)
    days_since_commit = (now - stats.last_commit_date).days

    # ── DEV_CANDIDATE gates ─────────────────────────────────────────────────
    dev_failures: list[str] = []

    if stats.contributors_count < dev_t.min_contributors:
        dev_failures.append(
            f"contributors {stats.contributors_count} < {dev_t.min_contributors} (commit-based lower bound)"
        )
    if stats.open_bug_issues > dev_t.max_open_bug_issues:
        dev_failures.append(
            f"open bug issues {stats.open_bug_issues} > {dev_t.max_open_bug_issues} allowed"
        )
    if days_since_commit > dev_t.max_days_since_last_commit:
        dev_failures.append(
            f"last commit {days_since_commit}d ago > {dev_t.max_days_since_last_commit}d threshold"
        )

    if dev_failures:
        return MaturityResult(level=MaturityLevel.NOT_READY, reasons=tuple(dev_failures))

    dev_passes: list[str] = [
        f"contributors ≥ {dev_t.min_contributors} ✓",
        f"open bug issues ≤ {dev_t.max_open_bug_issues} ✓",
        f"last commit {days_since_commit}d ago ≤ {dev_t.max_days_since_last_commit}d ✓",
    ]

    # ── PROD_CANDIDATE gates ────────────────────────────────────────────────
    prod_failures: list[str] = []

    if stats.contributors_count < prod_t.min_contributors:
        prod_failures.append(
            f"contributors {stats.contributors_count} < {prod_t.min_contributors} required for prod"
        )
    if stats.open_bug_issues > prod_t.max_open_bug_issues:
        prod_failures.append(
            f"open bug issues {stats.open_bug_issues} > {prod_t.max_open_bug_issues} allowed for prod"
        )
    if weeks_stable < prod_t.min_weeks_stable:
        prod_failures.append(
            f"only {weeks_stable} stable weeks; {prod_t.min_weeks_stable} required for prod"
        )
    if not stats.has_ci:
        prod_failures.append("no CI/CD pipeline detected (prod requires CI)")
    if stats.license_spdx is None:
        prod_failures.append("no OSS license detected (prod requires license)")

    if prod_failures:
        return MaturityResult(
            level=MaturityLevel.DEV_CANDIDATE,
            reasons=tuple(dev_passes + prod_failures),
        )

    prod_passes: list[str] = [
        f"contributors ≥ {prod_t.min_contributors} ✓",
        f"open bug issues ≤ {prod_t.max_open_bug_issues} ✓",
        f"{weeks_stable} stable weeks ≥ {prod_t.min_weeks_stable} ✓",
        "CI/CD present ✓",
        f"license: {stats.license_spdx} ✓",
    ]
    return MaturityResult(
        level=MaturityLevel.PROD_CANDIDATE,
        reasons=tuple(dev_passes + prod_passes),
    )
