"""services/repo_watch/scheduler.py — Weekly asyncio scheduler.

IL-093 | banxe-emi-stack

Starts a background asyncio task that runs WatchService.run_all() on a
configurable interval (default: 604 800 s = 7 days).

On startup it checks whether the interval has already elapsed since the last
known run (overdue check), and if so, fires immediately before entering the
sleep-loop.

Usage (in FastAPI lifespan):

    from services.repo_watch.scheduler import RepoWatchScheduler

    @asynccontextmanager
    async def lifespan(app):
        scheduler = RepoWatchScheduler(watch_service, interval_seconds=604800)
        scheduler.start()
        yield
        await scheduler.stop()
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
import logging

from services.repo_watch.watch_service import WatchService

logger = logging.getLogger("banxe.repo_watch.scheduler")


class RepoWatchScheduler:
    """Wraps WatchService in an asyncio background task.

    Args:
        service: Fully-wired WatchService instance.
        interval_seconds: How often to run (default: 604 800 = 7 days).
        run_on_startup_if_overdue: If True, fire immediately when the
            scheduler starts if more than *interval_seconds* have elapsed
            since *last_run_at* (or if *last_run_at* is None).
        last_run_at: Timestamp of the most recent successful run.  Persisted
            externally so the scheduler can survive API restarts.
    """

    def __init__(
        self,
        service: WatchService,
        *,
        interval_seconds: int = 604_800,
        run_on_startup_if_overdue: bool = True,
        last_run_at: datetime | None = None,
    ) -> None:
        self._service = service
        self._interval = interval_seconds
        self._run_on_startup_if_overdue = run_on_startup_if_overdue
        self._last_run_at = last_run_at
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    # ── Public API ───────────────────────────────────────────────────────────

    def start(self) -> None:
        """Schedule the background loop task."""
        if self._task is not None and not self._task.done():
            logger.warning("Scheduler already running; ignoring start()")
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop(), name="repo-watch-scheduler")
        logger.info("RepoWatchScheduler started (interval=%ds)", self._interval)

    async def stop(self) -> None:
        """Cancel the background task and wait for it to finish."""
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("RepoWatchScheduler stopped")

    @property
    def last_run_at(self) -> datetime | None:
        """Timestamp of the most recent successful cycle."""
        return self._last_run_at

    # ── Internal ─────────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        if self._run_on_startup_if_overdue and self._is_overdue():
            logger.info("Repo watch is overdue — running immediately on startup")
            await self._run_cycle()

        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=float(
                        self._interval
                    ),  # nosemgrep: banxe-float-money — seconds, not money
                )
            except TimeoutError:
                await self._run_cycle()

    async def _run_cycle(self) -> None:
        logger.info("Starting scheduled repo watch cycle")
        try:
            results = await self._service.run_all()
            self._last_run_at = datetime.now(tz=UTC)
            logger.info("Repo watch cycle complete: %d repo(s) checked", len(results))
        except Exception as exc:
            logger.error("Repo watch cycle failed: %s", exc)

    def _is_overdue(self) -> bool:
        if self._last_run_at is None:
            return True
        elapsed = (datetime.now(tz=UTC) - self._last_run_at).total_seconds()
        return elapsed >= self._interval
