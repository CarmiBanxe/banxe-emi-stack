"""Automatic CAMT.053 bank statement polling via adorsys PSD2.

Integrates with services/recon/camt053_parser.py for reconciliation pipeline.
IL-PSD2GW-01 | Phase 52B | Sprint 37
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import logging
from typing import Any, Protocol

logger = logging.getLogger("banxe.psd2_gateway.auto_pull")


@dataclass(frozen=True)
class PullSchedule:
    schedule_id: str
    iban: str
    frequency: str  # "daily" | "weekly"
    last_pull_at: str | None
    enabled: bool


class PullScheduleStorePort(Protocol):
    def append(self, schedule: PullSchedule) -> None: ...

    def list_active(self) -> list[PullSchedule]: ...

    def get(self, schedule_id: str) -> PullSchedule | None: ...


class InMemoryPullScheduleStore:
    def __init__(self) -> None:
        self._schedules: list[PullSchedule] = []

    def append(self, s: PullSchedule) -> None:
        self._schedules.append(s)

    def list_active(self) -> list[PullSchedule]:
        return [s for s in self._schedules if s.enabled]

    def get(self, sid: str) -> PullSchedule | None:
        return next((s for s in self._schedules if s.schedule_id == sid), None)


class AutoPuller:
    """Schedules automatic CAMT.053 fetches from adorsys PSD2 gateway."""

    def __init__(self, store: PullScheduleStorePort | None = None) -> None:
        self._store = store or InMemoryPullScheduleStore()

    def schedule(self, iban: str, frequency: str = "daily") -> PullSchedule:
        """Register auto-pull schedule for an IBAN. I-24 append-only."""
        schedule_id = f"pull_{hashlib.sha256(f'{iban}{frequency}'.encode()).hexdigest()[:8]}"
        schedule = PullSchedule(
            schedule_id=schedule_id,
            iban=iban,
            frequency=frequency,
            last_pull_at=None,
            enabled=True,
        )
        self._store.append(schedule)  # I-24
        logger.info("psd2.auto_pull_scheduled iban=%s*** freq=%s", iban[:6], frequency)
        return schedule

    def execute_pull(self, schedule_id: str) -> dict[str, Any]:
        """Execute a scheduled pull. Returns summary dict."""
        schedule = self._store.get(schedule_id)
        if schedule is None:
            raise KeyError(f"Schedule {schedule_id!r} not found")
        # In production: call adorsys → get CAMT.053 → parse → trigger recon
        # Stub: return summary
        return {
            "schedule_id": schedule_id,
            "iban": schedule.iban[:6] + "***",
            "status": "pulled",
            "pulled_at": datetime.now(UTC).isoformat(),
            "transactions_fetched": 0,  # stub — requires live bank connection
        }

    def list_active_schedules(self) -> list[PullSchedule]:
        return self._store.list_active()
