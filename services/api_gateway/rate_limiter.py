from __future__ import annotations

from datetime import UTC, datetime, timedelta

from services.api_gateway.models import (
    InMemoryRateLimitPolicyStore,
    RateLimitPolicy,
    RateLimitPolicyStorePort,
    RateLimitWindow,
    UsageTier,
)


class RateLimiter:
    """
    Token-bucket rate limiter (in-memory stub).
    Production: Redis-backed token bucket.
    """

    def __init__(self, policy_store: RateLimitPolicyStorePort | None = None) -> None:
        self._policy_store: RateLimitPolicyStorePort = (
            policy_store or InMemoryRateLimitPolicyStore()
        )
        self._buckets: dict[str, dict] = {}

    def _bucket_key(self, key_id: str, window: RateLimitWindow) -> str:
        return f"{key_id}:{window.value}"

    def _get_or_create_bucket(self, key_id: str, window: RateLimitWindow, limit: int) -> dict:
        bkey = self._bucket_key(key_id, window)
        now = datetime.now(UTC)
        if bkey not in self._buckets:
            self._buckets[bkey] = {
                "count": 0,
                "limit": limit,
                "window_start": now,
                "window": window,
            }
        return self._buckets[bkey]

    def check_rate_limit(self, key_id: str, tier: UsageTier) -> dict:
        """
        Check and increment rate limit counter.
        InMemory stub: always allowed=True.
        Returns {"allowed": bool, "remaining": int, "reset_at": str, "limit": int}.
        """
        policy = self._policy_store.get_policy(tier)
        if policy is None:
            return {
                "allowed": False,
                "remaining": 0,
                "reset_at": datetime.now(UTC).isoformat(),
                "limit": 0,
            }

        now = datetime.now(UTC)
        reset_at = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)

        bucket = self._get_or_create_bucket(
            key_id, RateLimitWindow.MINUTE, policy.requests_per_minute
        )
        bucket["count"] += 1

        remaining = max(0, policy.requests_per_minute - bucket["count"])

        return {
            "allowed": True,  # stub: always allowed
            "remaining": remaining,
            "reset_at": reset_at.isoformat(),
            "limit": policy.requests_per_minute,
        }

    def get_policy(self, tier: UsageTier) -> RateLimitPolicy | None:
        return self._policy_store.get_policy(tier)

    def reset_bucket(self, key_id: str) -> None:
        keys_to_delete = [k for k in self._buckets if k.startswith(f"{key_id}:")]
        for k in keys_to_delete:
            del self._buckets[k]
