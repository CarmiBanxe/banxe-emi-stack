from __future__ import annotations

from services.api_gateway.api_key_manager import APIKeyManager
from services.api_gateway.ip_filter import IPFilter
from services.api_gateway.models import UsageTier
from services.api_gateway.quota_manager import QuotaManager
from services.api_gateway.rate_limiter import RateLimiter
from services.api_gateway.request_logger import RequestLogger


class GatewayAgent:
    """
    Central API Gateway agent.
    Orchestrates: key management, rate limiting, quota, IP filtering, logging.
    Trust Zone AMBER | Autonomy L2 (L4 HITL for revocation per I-27).
    """

    def __init__(
        self,
        key_manager: APIKeyManager | None = None,
        rate_limiter: RateLimiter | None = None,
        quota_manager: QuotaManager | None = None,
        ip_filter: IPFilter | None = None,
        request_logger: RequestLogger | None = None,
    ) -> None:
        self._key_manager = key_manager or APIKeyManager()
        self._rate_limiter = rate_limiter or RateLimiter()
        self._quota_manager = quota_manager or QuotaManager()
        self._ip_filter = ip_filter or IPFilter()
        self._request_logger = request_logger or RequestLogger()

    def create_api_key(
        self,
        name: str,
        owner_id: str,
        scope: list[str],
        tier_str: str,
    ) -> dict:
        """
        Create a new API key.
        Returns {"raw_key": raw_key, "key_id": key_id, "tier": tier_str}.
        raw_key returned ONCE — never store it (I-12).
        """
        tier = UsageTier(tier_str)
        raw_key, api_key = self._key_manager.create_key(
            name=name, owner_id=owner_id, scope=scope, tier=tier
        )
        return {
            "raw_key": raw_key,
            "key_id": api_key.key_id,
            "tier": tier_str,
        }

    def check_request(
        self,
        raw_key: str,
        method: str,
        path: str,
        ip_address: str,
    ) -> dict:
        """
        Verify key → check rate limit → check quota → check IP → log.
        Returns {"allowed": bool, "key_id": str, "rate_limit": dict, "quota": dict}.
        """
        api_key = self._key_manager.verify_key(raw_key)
        if api_key is None:
            self._request_logger.log_request(
                key_id="unknown",
                method=method,
                path=path,
                status_code=401,
                latency_ms=0,
                ip_address=ip_address,
            )
            return {
                "allowed": False,
                "key_id": None,
                "rate_limit": {},
                "quota": {},
                "reason": "invalid_key",
            }

        if not self._ip_filter.is_allowed(ip_address, api_key.key_id):
            self._request_logger.log_request(
                key_id=api_key.key_id,
                method=method,
                path=path,
                status_code=403,
                latency_ms=0,
                ip_address=ip_address,
            )
            return {
                "allowed": False,
                "key_id": api_key.key_id,
                "rate_limit": {},
                "quota": {},
                "reason": "ip_blocked",
            }

        rate_limit = self._rate_limiter.check_rate_limit(api_key.key_id, api_key.tier)
        quota = self._quota_manager.check_quota(api_key.key_id, api_key.tier)

        allowed = rate_limit["allowed"] and quota["allowed"]
        status_code = 200 if allowed else 429

        self._quota_manager.increment_usage(api_key.key_id, api_key.tier)
        self._request_logger.log_request(
            key_id=api_key.key_id,
            method=method,
            path=path,
            status_code=status_code,
            latency_ms=0,
            ip_address=ip_address,
        )

        return {
            "allowed": allowed,
            "key_id": api_key.key_id,
            "rate_limit": rate_limit,
            "quota": quota,
        }

    def revoke_key(self, key_id: str, actor: str) -> dict:
        """Always returns HITL_REQUIRED (I-27) — Compliance Officer must approve."""
        return self._key_manager.revoke_key(key_id, actor)

    def get_usage_analytics(self, key_id: str) -> dict:
        """Return request analytics for a key."""
        analytics = self._request_logger.get_analytics(key_id)
        usage = self._quota_manager.get_usage_summary(key_id)
        return {
            "key_id": key_id,
            "analytics": analytics,
            "quota_summary": usage,
        }
