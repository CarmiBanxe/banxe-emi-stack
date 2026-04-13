"""services/repo_watch/notifier.py — Telegram notification sender.

IL-093 | banxe-emi-stack

Two notification types:
  1. Weekly digest: always sent on each scheduled check.
  2. Status-change alert: sent when maturity level changes (with dedup).

Deduplication:
  A status-change alert is suppressed if the same (owner, repo, new_level, date)
  key already appears in the alert store with a sent_at timestamp.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import Protocol

import httpx

from services.repo_watch.github_client import RepoStats
from services.repo_watch.maturity_evaluator import MaturityLevel, MaturityResult

logger = logging.getLogger("banxe.repo_watch.notifier")

_TG_API = "https://api.telegram.org"
_LEVEL_EMOJI = {
    MaturityLevel.NOT_READY: "🔴",
    MaturityLevel.DEV_CANDIDATE: "🟡",
    MaturityLevel.PROD_CANDIDATE: "🟢",
}


class NotifierPort(Protocol):
    """Notification abstraction (Telegram or stub)."""

    async def send_weekly_digest(
        self,
        owner: str,
        repo: str,
        stats: RepoStats,
        result: MaturityResult,
    ) -> bool:
        """Send the weekly maturity digest.  Returns True if sent."""
        ...  # noqa: PIE790

    async def send_status_change(
        self,
        owner: str,
        repo: str,
        prev_level: MaturityLevel | None,
        new_level: MaturityLevel,
        reasons: tuple[str, ...],
    ) -> bool:
        """Send a status-change alert.  Returns True if sent."""
        ...  # noqa: PIE790


# ── Telegram implementation ──────────────────────────────────────────────────


class TelegramNotifier:
    """Send notifications via the Telegram Bot API."""

    def __init__(self, bot_token: str, chat_id: str) -> None:
        if not bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN must be set")
        if not chat_id:
            raise ValueError("TELEGRAM_REPO_WATCH_CHAT_ID must be set")
        self._bot_token = bot_token
        self._chat_id = chat_id

    async def _send(self, text: str) -> bool:
        url = f"{_TG_API}/bot{self._bot_token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            logger.error("Telegram send failed: %s", exc)
            return False

    async def send_weekly_digest(
        self,
        owner: str,
        repo: str,
        stats: RepoStats,
        result: MaturityResult,
    ) -> bool:
        emoji = _LEVEL_EMOJI.get(result.level, "⚪")
        date_str = stats.fetched_at.strftime("%Y-%m-%d")
        days_since = (datetime.now(tz=UTC) - stats.last_commit_date).days
        text = (
            f"*GBrain Watch — Weekly Digest* ({date_str})\n\n"
            f"Repo: `{owner}/{repo}`\n"
            f"Maturity: {emoji} *{result.level.value}*\n\n"
            f"⭐ Stars: {stats.stars}  🍴 Forks: {stats.forks}\n"
            f"👥 Contributors: {stats.contributors_count} (commit-based)\n"
            f"🐛 Open bug issues: {stats.open_bug_issues}\n"
            f"📅 Last commit: {days_since}d ago\n"
            f"🔑 License: {stats.license_spdx or 'none'}\n"
            f"⚙️ CI: {'yes' if stats.has_ci else 'no'}\n\n"
            "Reasons:\n" + "\n".join(f"• {r}" for r in result.reasons)
        )
        logger.info("Sending weekly digest for %s/%s (level=%s)", owner, repo, result.level.value)
        return await self._send(text)

    async def send_status_change(
        self,
        owner: str,
        repo: str,
        prev_level: MaturityLevel | None,
        new_level: MaturityLevel,
        reasons: tuple[str, ...],
    ) -> bool:
        emoji = _LEVEL_EMOJI.get(new_level, "⚪")
        prev_str = prev_level.value if prev_level else "none"
        text = (
            f"*GBrain Watch — Status Change* ⚠️\n\n"
            f"Repo: `{owner}/{repo}`\n"
            f"Change: `{prev_str}` → {emoji} *{new_level.value}*\n\n"
            "Reasons:\n" + "\n".join(f"• {r}" for r in reasons)
        )
        logger.info(
            "Sending status-change alert for %s/%s: %s → %s",
            owner,
            repo,
            prev_str,
            new_level.value,
        )
        return await self._send(text)


# ── In-memory stub for tests ─────────────────────────────────────────────────


class InMemoryNotifier:
    """Records sent notifications without making HTTP calls."""

    def __init__(self) -> None:
        self.digests: list[dict[str, object]] = []
        self.changes: list[dict[str, object]] = []
        self._should_fail: bool = False

    def set_fail(self, *, fail: bool = True) -> None:
        """Configure the stub to simulate send failure."""
        self._should_fail = fail

    async def send_weekly_digest(
        self,
        owner: str,
        repo: str,
        stats: RepoStats,
        result: MaturityResult,
    ) -> bool:
        if self._should_fail:
            return False
        self.digests.append({"owner": owner, "repo": repo, "level": result.level.value})
        return True

    async def send_status_change(
        self,
        owner: str,
        repo: str,
        prev_level: MaturityLevel | None,
        new_level: MaturityLevel,
        reasons: tuple[str, ...],
    ) -> bool:
        if self._should_fail:
            return False
        self.changes.append(
            {
                "owner": owner,
                "repo": repo,
                "prev": prev_level.value if prev_level else None,
                "new": new_level.value,
            }
        )
        return True
