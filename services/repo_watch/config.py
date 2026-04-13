"""services/repo_watch/config.py — GBrain Watch Agent configuration.

IL-093 | banxe-emi-stack

Loads from YAML (config/gbrain_watch.yaml) with env-var overrides for
secrets (GITHUB_TOKEN, TELEGRAM_REPO_WATCH_CHAT_ID, REPO_WATCH_INTERNAL_KEY).
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_YAML = Path("config/gbrain_watch.yaml")


@dataclass(frozen=True)
class DevCandidateThresholds:
    """Minimum bar for dev/staging environment usage."""

    min_contributors: int = 3
    max_open_bug_issues: int = 5
    max_days_since_last_commit: int = 7
    min_weeks_observed: int = 4


@dataclass(frozen=True)
class ProdCandidateThresholds:
    """Minimum bar for production compliance-agent usage."""

    min_contributors: int = 5
    max_open_bug_issues: int = 2
    min_weeks_stable: int = 12


@dataclass(frozen=True)
class CriticalIssueLabels:
    """GitHub issue labels treated as 'critical bugs' for maturity scoring."""

    labels: tuple[str, ...] = ("bug", "security", "vulnerability", "critical", "regression")


@dataclass(frozen=True)
class WatchedRepo:
    """One entry in the watched-repos list."""

    owner: str
    repo: str
    reason: str = ""


@dataclass(frozen=True)
class RepoWatchConfig:
    """Parsed, frozen configuration for the Repo Watch service."""

    repos: tuple[WatchedRepo, ...]
    dev_candidate: DevCandidateThresholds
    prod_candidate: ProdCandidateThresholds
    critical_issue_labels: CriticalIssueLabels
    check_interval_seconds: int = 604_800  # 7 days
    telegram_chat_id: str = ""
    github_token: str = ""
    internal_api_key: str = ""


# ── Loaders ─────────────────────────────────────────────────────────────────


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


def load_config(yaml_path: Path | None = None) -> RepoWatchConfig:
    """Load config from YAML + env-var overrides.

    Args:
        yaml_path: Optional explicit path to the YAML config file.
                   Defaults to ``REPO_WATCH_CONFIG`` env var or
                   ``config/gbrain_watch.yaml``.

    Returns:
        Frozen :class:`RepoWatchConfig`.
    """
    path = yaml_path or Path(os.environ.get("REPO_WATCH_CONFIG", str(_DEFAULT_YAML)))
    raw: dict[str, Any] = _load_yaml(path) if path.exists() else {}

    repos = tuple(
        WatchedRepo(owner=r["owner"], repo=r["repo"], reason=r.get("reason", ""))
        for r in raw.get("repos", [])
    )

    dev_raw: dict[str, Any] = raw.get("thresholds", {}).get("dev_candidate", {})
    dev = DevCandidateThresholds(
        min_contributors=int(dev_raw.get("min_contributors", 3)),
        max_open_bug_issues=int(dev_raw.get("max_open_bug_issues", 5)),
        max_days_since_last_commit=int(dev_raw.get("max_days_since_last_commit", 7)),
        min_weeks_observed=int(dev_raw.get("min_weeks_observed", 4)),
    )

    prod_raw: dict[str, Any] = raw.get("thresholds", {}).get("prod_candidate", {})
    prod = ProdCandidateThresholds(
        min_contributors=int(prod_raw.get("min_contributors", 5)),
        max_open_bug_issues=int(prod_raw.get("max_open_bug_issues", 2)),
        min_weeks_stable=int(prod_raw.get("min_weeks_stable", 12)),
    )

    labels_raw: list[str] = raw.get("critical_issue_labels", [])
    labels = CriticalIssueLabels(labels=tuple(labels_raw)) if labels_raw else CriticalIssueLabels()

    return RepoWatchConfig(
        repos=repos,
        dev_candidate=dev,
        prod_candidate=prod,
        critical_issue_labels=labels,
        check_interval_seconds=int(raw.get("check_interval_seconds", 604_800)),
        telegram_chat_id=os.environ.get(
            "TELEGRAM_REPO_WATCH_CHAT_ID", raw.get("telegram_chat_id", "")
        ),
        github_token=os.environ.get("GITHUB_TOKEN", raw.get("github_token", "")),
        internal_api_key=os.environ.get("REPO_WATCH_INTERNAL_KEY", raw.get("internal_api_key", "")),
    )


def make_in_memory_config(
    owner: str = "garrytan",
    repo: str = "gbrain",
    *,
    min_contributors: int = 3,
    max_open_bug_issues: int = 5,
) -> RepoWatchConfig:
    """Return a minimal in-memory config for tests."""
    return RepoWatchConfig(
        repos=(WatchedRepo(owner=owner, repo=repo, reason="test"),),
        dev_candidate=DevCandidateThresholds(
            min_contributors=min_contributors,
            max_open_bug_issues=max_open_bug_issues,
        ),
        prod_candidate=ProdCandidateThresholds(),
        critical_issue_labels=CriticalIssueLabels(),
        check_interval_seconds=604_800,
    )
