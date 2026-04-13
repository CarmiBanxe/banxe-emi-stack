"""services/repo_watch/github_client.py — Async GitHub REST API client.

IL-093 | banxe-emi-stack

NOTE — Contributors API limitation:
    GET /repos/{owner}/{repo}/contributors counts *commit-based* contributions only.
    Contributors who participate exclusively through reviews, issues, or discussions
    without making direct commits will NOT appear in this count.
    Use the result as a lower-bound proxy, not an exact headcount.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import logging
import time
from typing import Any, Protocol

import httpx

logger = logging.getLogger("banxe.repo_watch.github")

_GITHUB_API = "https://api.github.com"
_USER_AGENT = "banxe-emi-stack/1.0 (GBrain Watch Agent IL-093)"
_RATE_LIMIT_MAX_WAIT_SECS = 120


@dataclass
class RepoStats:
    """Point-in-time snapshot of a GitHub repository's public metrics."""

    owner: str
    repo: str
    stars: int
    forks: int
    open_issues: int
    open_bug_issues: int
    contributors_count: int  # commit-based lower bound; see module docstring
    last_commit_date: datetime
    default_branch: str
    license_spdx: str | None
    is_archived: bool
    has_ci: bool
    fetched_at: datetime


class GitHubClientPort(Protocol):
    """Protocol for any GitHub data source (real or stub)."""

    async def fetch_repo_stats(self, owner: str, repo: str) -> RepoStats:
        """Fetch all metrics for *owner*/*repo*."""
        ...  # noqa: PIE790


class GitHubRateLimitError(Exception):
    """Raised when the GitHub rate limit is exhausted with no safe wait time."""

    def __init__(self, reset_at: datetime) -> None:
        super().__init__(f"Rate limit exhausted; resets at {reset_at.isoformat()}")
        self.reset_at = reset_at


class GitHubClient:
    """Async GitHub REST API client with automatic rate-limit back-off."""

    def __init__(
        self, token: str = "", timeout: float = 30.0
    ) -> None:  # nosemgrep: banxe-float-money — HTTP timeout, not money
        self._token = token
        self._timeout = timeout

    # ── Internals ────────────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "User-Agent": _USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    async def _get(self, client: httpx.AsyncClient, url: str) -> Any:
        """GET *url* with one rate-limit retry if remaining quota is zero."""
        resp = await client.get(url, headers=self._headers(), timeout=self._timeout)

        remaining = int(resp.headers.get("X-RateLimit-Remaining", "1"))
        reset_ts = int(resp.headers.get("X-RateLimit-Reset", str(int(time.time()) + 60)))

        if resp.status_code == 429 or remaining == 0:
            reset_dt = datetime.fromtimestamp(reset_ts, tz=UTC)
            wait_secs = max(0, reset_ts - int(time.time())) + 5
            if wait_secs > _RATE_LIMIT_MAX_WAIT_SECS:
                raise GitHubRateLimitError(reset_dt)
            logger.warning(
                "GitHub rate limit hit; sleeping %ds (resets %s)", wait_secs, reset_dt.isoformat()
            )
            await asyncio.sleep(wait_secs)
            resp = await client.get(url, headers=self._headers(), timeout=self._timeout)

        resp.raise_for_status()
        return resp.json()

    async def _check_ci(self, client: httpx.AsyncClient, base: str) -> bool:
        """Return True if a .github/workflows directory exists in the repo."""
        try:
            data = await self._get(client, f"{base}/contents/.github/workflows")
            return bool(data)
        except httpx.HTTPStatusError as exc:
            return exc.response.status_code != 404

    # ── Public API ───────────────────────────────────────────────────────────

    async def fetch_repo_stats(self, owner: str, repo: str) -> RepoStats:
        """Fetch all metrics for *owner*/*repo* in a single client session.

        Makes 4–5 GitHub API calls:
        - GET /repos/{owner}/{repo}
        - GET /repos/{owner}/{repo}/contributors
        - GET /repos/{owner}/{repo}/issues (bug labels only)
        - GET /repos/{owner}/{repo}/commits (last commit)
        - GET /repos/{owner}/{repo}/contents/.github/workflows (CI probe)
        """
        base = f"{_GITHUB_API}/repos/{owner}/{repo}"
        fetched_at = datetime.now(tz=UTC)

        async with httpx.AsyncClient() as client:
            repo_data: dict[str, Any] = await self._get(client, base)
            contributors_data: list[Any] = await self._get(
                client, f"{base}/contributors?per_page=100&anon=false"
            )
            labels_q = "bug+security+vulnerability+critical+regression"
            issues_data: list[Any] = await self._get(
                client,
                f"{base}/issues?state=open&labels={labels_q}&per_page=100",
            )
            commits_data: list[Any] = await self._get(
                client, f"{_GITHUB_API}/repos/{owner}/{repo}/commits?per_page=1"
            )
            has_ci = await self._check_ci(client, base)

        # ── Last-commit date ──────────────────────────────────────────────
        last_commit_date = fetched_at
        if commits_data:
            raw_date: str = commits_data[0].get("commit", {}).get("committer", {}).get(
                "date", ""
            ) or commits_data[0].get("commit", {}).get("author", {}).get("date", "")
            if raw_date:
                last_commit_date = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))

        # ── License ───────────────────────────────────────────────────────
        license_spdx: str | None = None
        license_info = repo_data.get("license")
        if isinstance(license_info, dict):
            license_spdx = license_info.get("spdx_id") or None

        return RepoStats(
            owner=owner,
            repo=repo,
            stars=int(repo_data.get("stargazers_count", 0)),
            forks=int(repo_data.get("forks_count", 0)),
            open_issues=int(repo_data.get("open_issues_count", 0)),
            open_bug_issues=len(issues_data) if isinstance(issues_data, list) else 0,
            contributors_count=len(contributors_data) if isinstance(contributors_data, list) else 0,
            last_commit_date=last_commit_date,
            default_branch=str(repo_data.get("default_branch", "main")),
            license_spdx=license_spdx,
            is_archived=bool(repo_data.get("archived", False)),
            has_ci=has_ci,
            fetched_at=fetched_at,
        )


# ── In-memory stub for tests ─────────────────────────────────────────────────


class InMemoryGitHubClient:
    """Deterministic GitHub stub for unit tests.

    Pass ``stats=`` to control the returned value, or leave it *None* to get
    a healthy repo that passes both DEV_CANDIDATE and PROD_CANDIDATE gates.
    """

    def __init__(self, stats: RepoStats | None = None) -> None:
        self._stats = stats

    async def fetch_repo_stats(self, owner: str, repo: str) -> RepoStats:
        """Return the pre-configured stats, or a default healthy snapshot."""
        if self._stats is not None:
            return self._stats
        now = datetime.now(tz=UTC)
        return RepoStats(
            owner=owner,
            repo=repo,
            stars=200,
            forks=18,
            open_issues=4,
            open_bug_issues=1,
            contributors_count=6,
            last_commit_date=now,
            default_branch="main",
            license_spdx="MIT",
            is_archived=False,
            has_ci=True,
            fetched_at=now,
        )
