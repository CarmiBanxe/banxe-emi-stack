"""services/repo_watch/watch_service.py — Orchestration for one watch cycle.

IL-093 | banxe-emi-stack

WatchService.run_all():
  For each configured repo:
    1. Fetch stats from GitHub
    2. Count stable weeks from store
    3. Evaluate maturity
    4. Save snapshot to store
    5. Send weekly digest via notifier
    6. If level changed: send status-change alert (dedup guard)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
import uuid

from services.repo_watch.config import RepoWatchConfig
from services.repo_watch.github_client import GitHubClientPort, RepoStats
from services.repo_watch.maturity_evaluator import (
    MaturityLevel,
    MaturityResult,
    evaluate_maturity,
)
from services.repo_watch.notifier import NotifierPort
from services.repo_watch.store import (
    AlertRecord,
    RepoWatchStorePort,
    SnapshotRecord,
    make_dedup_key,
)

logger = logging.getLogger("banxe.repo_watch.service")


@dataclass
class RepoCheckResult:
    """Output of a single repo check cycle."""

    owner: str
    repo: str
    maturity: MaturityResult
    level_changed: bool
    prev_level: MaturityLevel | None
    digest_sent: bool
    alert_sent: bool


class WatchService:
    """Orchestrate a full watch cycle across all configured repositories."""

    def __init__(
        self,
        config: RepoWatchConfig,
        github: GitHubClientPort,
        store: RepoWatchStorePort,
        notifier: NotifierPort,
    ) -> None:
        self._config = config
        self._github = github
        self._store = store
        self._notifier = notifier

    # ── Public API ───────────────────────────────────────────────────────────

    async def run_all(self) -> list[RepoCheckResult]:
        """Run a watch cycle for every repo in config.repos."""
        results: list[RepoCheckResult] = []
        for watched in self._config.repos:
            try:
                result = await self._check_one(watched.owner, watched.repo)
                results.append(result)
            except Exception as exc:
                logger.error("Watch cycle failed for %s/%s: %s", watched.owner, watched.repo, exc)
        return results

    async def check_one(self, owner: str, repo: str) -> RepoCheckResult:
        """Run a watch cycle for a single repo (used by manual trigger API)."""
        return await self._check_one(owner, repo)

    # ── Internal ─────────────────────────────────────────────────────────────

    async def _check_one(self, owner: str, repo: str) -> RepoCheckResult:
        logger.info("Checking %s/%s", owner, repo)

        stats: RepoStats = await self._github.fetch_repo_stats(owner, repo)

        weeks_stable = await self._store.count_stable_weeks(
            owner, repo, MaturityLevel.DEV_CANDIDATE
        )

        maturity = evaluate_maturity(stats, self._config, weeks_stable=weeks_stable)

        snap = _to_snapshot(stats, maturity)
        await self._store.save_snapshot(snap)

        digest_sent = await self._notifier.send_weekly_digest(owner, repo, stats, maturity)

        prev_snap = await self._store.get_latest_snapshot(owner, repo)
        prev_level: MaturityLevel | None = None
        if prev_snap is not None and prev_snap.id != snap.id:
            try:
                prev_level = MaturityLevel(prev_snap.maturity_level)
            except ValueError:
                prev_level = None

        level_changed = prev_level is not None and prev_level != maturity.level

        alert_sent = False
        if level_changed:
            today_str = datetime.now(tz=UTC).strftime("%Y-%m-%d")
            dedup_key = make_dedup_key(owner, repo, maturity.level.value, today_str)
            already_sent = await self._store.alert_already_sent(dedup_key)
            if not already_sent:
                sent = await self._notifier.send_status_change(
                    owner, repo, prev_level, maturity.level, maturity.reasons
                )
                alert_record = AlertRecord(
                    id=str(uuid.uuid4()),
                    owner=owner,
                    repo=repo,
                    prev_maturity_level=prev_level.value if prev_level else None,
                    new_maturity_level=maturity.level.value,
                    message="; ".join(maturity.reasons),
                    sent_at=datetime.now(tz=UTC) if sent else None,
                    dedup_key=dedup_key,
                )
                await self._store.record_alert(alert_record)
                alert_sent = sent

        return RepoCheckResult(
            owner=owner,
            repo=repo,
            maturity=maturity,
            level_changed=level_changed,
            prev_level=prev_level,
            digest_sent=digest_sent,
            alert_sent=alert_sent,
        )


# ── Helpers ──────────────────────────────────────────────────────────────────


def _to_snapshot(stats: RepoStats, maturity: MaturityResult) -> SnapshotRecord:
    return SnapshotRecord(
        id=str(uuid.uuid4()),
        owner=stats.owner,
        repo=stats.repo,
        stars=stats.stars,
        forks=stats.forks,
        open_issues=stats.open_issues,
        open_bug_issues=stats.open_bug_issues,
        contributors_count=stats.contributors_count,
        last_commit_date=stats.last_commit_date,
        maturity_level=maturity.level.value,
        maturity_reason="; ".join(maturity.reasons),
        is_archived=stats.is_archived,
        has_ci=stats.has_ci,
        license_spdx=stats.license_spdx,
        fetched_at=stats.fetched_at,
    )
