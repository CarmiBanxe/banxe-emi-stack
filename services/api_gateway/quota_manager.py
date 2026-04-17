from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, time
import uuid

from services.api_gateway.models import (
    InMemoryQuotaStore,
    InMemoryRateLimitPolicyStore,
    QuotaStorePort,
    QuotaUsage,
    RateLimitPolicyStorePort,
    UsageTier,
)

_SOFT_LIMIT_PCT = 0.8
_HARD_LIMIT_PCT = 1.0


def _day_window_start(now: datetime) -> datetime:
    return datetime.combine(now.date(), time.min, tzinfo=UTC)


def _day_window_end(now: datetime) -> datetime:
    return datetime.combine(now.date(), time.max, tzinfo=UTC)


class QuotaManager:
    """Daily quota management with soft (80%) and hard (100%) limits."""

    def __init__(
        self,
        quota_store: QuotaStorePort | None = None,
        policy_store: RateLimitPolicyStorePort | None = None,
    ) -> None:
        self._quota_store: QuotaStorePort = quota_store or InMemoryQuotaStore()
        self._policy_store: RateLimitPolicyStorePort = (
            policy_store or InMemoryRateLimitPolicyStore()
        )

    def _daily_limit(self, tier: UsageTier) -> int:
        policy = self._policy_store.get_policy(tier)
        return policy.requests_per_hour * 24 if policy else 0

    def check_quota(self, key_id: str, tier: UsageTier) -> dict:
        """
        Returns {"allowed": bool, "used": int, "limit": int, "reset_at": str}.
        Soft limit at 80%: warning (still allowed).
        Hard limit at 100%: blocked.
        """
        now = datetime.now(UTC)
        window_start = _day_window_start(now)
        window_end = _day_window_end(now)
        daily_limit = self._daily_limit(tier)

        usage = self._quota_store.get_current(key_id, window_start)
        used = usage.request_count if usage else 0

        allowed = used < daily_limit * _HARD_LIMIT_PCT if daily_limit > 0 else True

        return {
            "allowed": allowed,
            "used": used,
            "limit": daily_limit,
            "reset_at": window_end.isoformat(),
            "warning": used >= daily_limit * _SOFT_LIMIT_PCT if daily_limit > 0 else False,
        }

    def increment_usage(self, key_id: str, tier: UsageTier) -> QuotaUsage:
        """Increment daily usage counter, create record if not exists."""
        now = datetime.now(UTC)
        window_start = _day_window_start(now)
        window_end = _day_window_end(now)

        existing = self._quota_store.get_current(key_id, window_start)
        if existing is None:
            new_usage = QuotaUsage(
                usage_id=str(uuid.uuid4()),
                key_id=key_id,
                window_start=window_start,
                window_end=window_end,
                request_count=1,
                tier=tier,
                updated_at=now,
            )
            self._quota_store.save(new_usage)
            return new_usage

        updated = replace(
            existing,
            request_count=existing.request_count + 1,
            updated_at=now,
        )
        self._quota_store.save(updated)
        return updated

    def get_usage_summary(self, key_id: str) -> dict:
        """Return usage summary across all recorded windows."""
        history = self._quota_store.get_history(key_id)
        if not history:
            return {"key_id": key_id, "total_windows": 0, "records": []}

        records = [
            {
                "window_start": q.window_start.isoformat(),
                "window_end": q.window_end.isoformat(),
                "request_count": q.request_count,
                "tier": q.tier.value,
            }
            for q in history
        ]
        return {
            "key_id": key_id,
            "total_windows": len(history),
            "records": records,
        }
