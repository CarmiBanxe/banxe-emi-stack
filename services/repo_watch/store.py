"""services/repo_watch/store.py — Persistence layer (Protocol DI pattern).

IL-093 | banxe-emi-stack

Defines RepoWatchStorePort and InMemoryRepoWatchStore.
Production implementation (PostgresRepoWatchStore) uses asyncpg directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from services.repo_watch.maturity_evaluator import MaturityLevel

# ── Data transfer objects ────────────────────────────────────────────────────


@dataclass
class SnapshotRecord:
    """Persisted weekly snapshot row."""

    id: str
    owner: str
    repo: str
    stars: int
    forks: int
    open_issues: int
    open_bug_issues: int
    contributors_count: int
    last_commit_date: datetime
    maturity_level: str
    maturity_reason: str
    is_archived: bool
    has_ci: bool
    license_spdx: str | None
    fetched_at: datetime


@dataclass
class AlertRecord:
    """Persisted alert row (sent or pending)."""

    id: str
    owner: str
    repo: str
    prev_maturity_level: str | None
    new_maturity_level: str
    message: str
    sent_at: datetime | None
    dedup_key: str


# ── Protocol ────────────────────────────────────────────────────────────────


class RepoWatchStorePort(Protocol):
    """Persistence contract for the Repo Watch service."""

    async def save_snapshot(self, snap: SnapshotRecord) -> None:
        """Persist a weekly snapshot row."""
        ...  # noqa: PIE790

    async def get_snapshots(
        self, owner: str, repo: str, *, limit: int = 52
    ) -> list[SnapshotRecord]:
        """Return up to *limit* snapshots, newest first."""
        ...  # noqa: PIE790

    async def count_stable_weeks(self, owner: str, repo: str, since_level: MaturityLevel) -> int:
        """Count consecutive recent weeks at or above *since_level*."""
        ...  # noqa: PIE790

    async def alert_already_sent(self, dedup_key: str) -> bool:
        """Return True if an alert with this dedup key was already sent today."""
        ...  # noqa: PIE790

    async def record_alert(self, alert: AlertRecord) -> None:
        """Persist an alert record (whether sent or suppressed by dedup)."""
        ...  # noqa: PIE790

    async def get_latest_snapshot(self, owner: str, repo: str) -> SnapshotRecord | None:
        """Return the most recent snapshot for *owner*/*repo*, or None."""
        ...  # noqa: PIE790


# ── In-memory store (tests) ─────────────────────────────────────────────────


class InMemoryRepoWatchStore:
    """Thread-safe-enough in-memory implementation for unit tests."""

    def __init__(self) -> None:
        self._snapshots: list[SnapshotRecord] = []
        self._alerts: list[AlertRecord] = []

    async def save_snapshot(self, snap: SnapshotRecord) -> None:
        self._snapshots.append(snap)

    async def get_snapshots(
        self, owner: str, repo: str, *, limit: int = 52
    ) -> list[SnapshotRecord]:
        rows = [s for s in self._snapshots if s.owner == owner and s.repo == repo]
        rows.sort(key=lambda s: s.fetched_at, reverse=True)
        return rows[:limit]

    async def count_stable_weeks(self, owner: str, repo: str, since_level: MaturityLevel) -> int:
        rows = await self.get_snapshots(owner, repo)
        count = 0
        for row in rows:
            try:
                level = MaturityLevel(row.maturity_level)
            except ValueError:
                break
            level_order = {
                MaturityLevel.NOT_READY: 0,
                MaturityLevel.DEV_CANDIDATE: 1,
                MaturityLevel.PROD_CANDIDATE: 2,
            }
            if level_order[level] >= level_order[since_level]:
                count += 1
            else:
                break
        return count

    async def alert_already_sent(self, dedup_key: str) -> bool:
        return any(a.dedup_key == dedup_key and a.sent_at is not None for a in self._alerts)

    async def record_alert(self, alert: AlertRecord) -> None:
        self._alerts.append(alert)

    async def get_latest_snapshot(self, owner: str, repo: str) -> SnapshotRecord | None:
        rows = await self.get_snapshots(owner, repo, limit=1)
        return rows[0] if rows else None


# ── Postgres store (production) ──────────────────────────────────────────────


class PostgresRepoWatchStore:
    """asyncpg-backed production store.

    Requires the ``repo_watch_snapshots`` and ``repo_watch_alerts`` tables
    created by Alembic migration ``a1b2c3d4e5f6``.
    """

    def __init__(self, pool: object) -> None:
        # pool: asyncpg.Pool — typed as object to avoid import at module level
        self._pool = pool

    async def save_snapshot(self, snap: SnapshotRecord) -> None:
        sql = """
            INSERT INTO repo_watch_snapshots
              (id, owner, repo, stars, forks, open_issues, open_bug_issues,
               contributors_count, last_commit_date, maturity_level, maturity_reason,
               is_archived, has_ci, license_spdx, fetched_at)
            VALUES
              ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
            ON CONFLICT (id) DO NOTHING
        """
        await self._pool.execute(  # type: ignore[union-attr]
            sql,
            snap.id,
            snap.owner,
            snap.repo,
            snap.stars,
            snap.forks,
            snap.open_issues,
            snap.open_bug_issues,
            snap.contributors_count,
            snap.last_commit_date,
            snap.maturity_level,
            snap.maturity_reason,
            snap.is_archived,
            snap.has_ci,
            snap.license_spdx,
            snap.fetched_at,
        )

    async def get_snapshots(
        self, owner: str, repo: str, *, limit: int = 52
    ) -> list[SnapshotRecord]:
        sql = """
            SELECT id, owner, repo, stars, forks, open_issues, open_bug_issues,
                   contributors_count, last_commit_date, maturity_level, maturity_reason,
                   is_archived, has_ci, license_spdx, fetched_at
            FROM repo_watch_snapshots
            WHERE owner=$1 AND repo=$2
            ORDER BY fetched_at DESC
            LIMIT $3
        """
        rows = await self._pool.fetch(sql, owner, repo, limit)  # type: ignore[union-attr]
        return [SnapshotRecord(**dict(r)) for r in rows]

    async def count_stable_weeks(self, owner: str, repo: str, since_level: MaturityLevel) -> int:
        rows = await self.get_snapshots(owner, repo)
        count = 0
        level_order = {
            MaturityLevel.NOT_READY: 0,
            MaturityLevel.DEV_CANDIDATE: 1,
            MaturityLevel.PROD_CANDIDATE: 2,
        }
        for row in rows:
            try:
                level = MaturityLevel(row.maturity_level)
            except ValueError:
                break
            if level_order[level] >= level_order[since_level]:
                count += 1
            else:
                break
        return count

    async def alert_already_sent(self, dedup_key: str) -> bool:
        sql = "SELECT 1 FROM repo_watch_alerts WHERE dedup_key=$1 AND sent_at IS NOT NULL LIMIT 1"
        row = await self._pool.fetchrow(sql, dedup_key)  # type: ignore[union-attr]
        return row is not None

    async def record_alert(self, alert: AlertRecord) -> None:
        sql = """
            INSERT INTO repo_watch_alerts
              (id, owner, repo, prev_maturity_level, new_maturity_level,
               message, sent_at, dedup_key)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            ON CONFLICT (dedup_key) DO UPDATE SET sent_at=EXCLUDED.sent_at
        """
        await self._pool.execute(  # type: ignore[union-attr]
            sql,
            alert.id,
            alert.owner,
            alert.repo,
            alert.prev_maturity_level,
            alert.new_maturity_level,
            alert.message,
            alert.sent_at,
            alert.dedup_key,
        )

    async def get_latest_snapshot(self, owner: str, repo: str) -> SnapshotRecord | None:
        rows = await self.get_snapshots(owner, repo, limit=1)
        return rows[0] if rows else None


def make_dedup_key(owner: str, repo: str, new_level: str, date_str: str) -> str:
    """Build a deduplication key scoped to *owner/repo*, *new_level*, and *date* (YYYY-MM-DD)."""
    return f"{owner}/{repo}/{new_level}/{date_str}"
