from __future__ import annotations

from datetime import UTC, datetime
import uuid

from services.api_gateway.models import (
    InMemoryRequestLogStore,
    RequestLog,
    RequestLogStorePort,
)


class RequestLogger:
    """
    Append-only request logger (I-24).
    Analytics: success_rate and avg_latency_ms use float (analytical, not monetary).
    """

    def __init__(self, store: RequestLogStorePort | None = None) -> None:
        self._store: RequestLogStorePort = store or InMemoryRequestLogStore()

    def log_request(
        self,
        key_id: str,
        method: str,
        path: str,
        status_code: int,
        latency_ms: int,
        ip_address: str,
    ) -> RequestLog:
        """Create and append a RequestLog record (I-24 append-only)."""
        log = RequestLog(
            log_id=str(uuid.uuid4()),
            key_id=key_id,
            method=method,
            path=path,
            status_code=status_code,
            latency_ms=latency_ms,
            timestamp=datetime.now(UTC),
            ip_address=ip_address,
        )
        self._store.append(log)
        return log

    def get_analytics(self, key_id: str, limit: int = 100) -> dict:
        """
        Returns analytics for a key.
        success_rate: float (analytical score, not monetary).
        avg_latency_ms: float (analytical score, not monetary).
        """
        logs = self._store.list_by_key(key_id, limit=limit)
        total = len(logs)
        if total == 0:
            return {
                "total_requests": 0,
                "success_rate": 0.0,
                "avg_latency_ms": 0.0,
                "recent_logs": [],
            }

        success_count = sum(1 for lg in logs if 200 <= lg.status_code < 300)
        success_rate: float = success_count / total
        avg_latency: float = sum(lg.latency_ms for lg in logs) / total

        recent = [
            {
                "log_id": lg.log_id,
                "method": lg.method,
                "path": lg.path,
                "status_code": lg.status_code,
                "latency_ms": lg.latency_ms,
                "timestamp": lg.timestamp.isoformat(),
            }
            for lg in logs[-10:]
        ]

        return {
            "total_requests": total,
            "success_rate": success_rate,
            "avg_latency_ms": avg_latency,
            "recent_logs": recent,
        }

    def get_usage_by_path(self, key_id: str) -> dict:
        """Returns {'/v1/path': count} breakdown."""
        logs = self._store.list_by_key(key_id, limit=10000)
        counts: dict[str, int] = {}
        for lg in logs:
            counts[lg.path] = counts.get(lg.path, 0) + 1
        return counts
