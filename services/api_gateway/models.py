from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol
import uuid


class UsageTier(str, Enum):
    FREE = "FREE"
    BASIC = "BASIC"
    PREMIUM = "PREMIUM"
    ENTERPRISE = "ENTERPRISE"


class KeyStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ROTATED = "ROTATED"
    REVOKED = "REVOKED"


class RateLimitWindow(str, Enum):
    SECOND = "SECOND"
    MINUTE = "MINUTE"
    HOUR = "HOUR"
    DAY = "DAY"


class GeoAction(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class APIKey:
    key_id: str
    name: str
    key_hash: str  # SHA-256 of raw key — never store raw (I-12)
    scope: list[str]
    tier: UsageTier
    status: KeyStatus
    created_at: datetime
    rotated_at: datetime | None = None
    revoked_at: datetime | None = None
    owner_id: str = ""


@dataclass(frozen=True)
class RateLimitPolicy:
    policy_id: str
    tier: UsageTier
    requests_per_second: int
    requests_per_minute: int
    requests_per_hour: int
    burst_allowance: int
    created_at: datetime


@dataclass(frozen=True)
class QuotaUsage:
    usage_id: str
    key_id: str
    window_start: datetime
    window_end: datetime
    request_count: int
    tier: UsageTier
    updated_at: datetime


@dataclass(frozen=True)
class RequestLog:
    log_id: str
    key_id: str
    method: str
    path: str
    status_code: int  # not monetary — int OK
    latency_ms: int  # not monetary — int OK
    timestamp: datetime
    ip_address: str


@dataclass(frozen=True)
class IPAllowlistEntry:
    entry_id: str
    key_id: str
    cidr: str
    action: GeoAction
    created_at: datetime


# ---------------------------------------------------------------------------
# Protocols (DI ports)
# ---------------------------------------------------------------------------


class APIKeyStorePort(Protocol):
    def save(self, k: APIKey) -> None: ...
    def get_by_id(self, key_id: str) -> APIKey | None: ...
    def get_by_hash(self, key_hash: str) -> APIKey | None: ...
    def list_by_owner(self, owner_id: str) -> list[APIKey]: ...
    def update(self, k: APIKey) -> None: ...


class RateLimitPolicyStorePort(Protocol):
    def get_policy(self, tier: UsageTier) -> RateLimitPolicy | None: ...
    def save(self, p: RateLimitPolicy) -> None: ...


class QuotaStorePort(Protocol):
    def save(self, q: QuotaUsage) -> None: ...
    def get_current(self, key_id: str, window_start: datetime) -> QuotaUsage | None: ...
    def get_history(self, key_id: str) -> list[QuotaUsage]: ...


class RequestLogStorePort(Protocol):
    def append(self, log: RequestLog) -> None: ...
    def list_by_key(self, key_id: str, limit: int = 100) -> list[RequestLog]: ...


class IPAllowlistStorePort(Protocol):
    def save(self, e: IPAllowlistEntry) -> None: ...
    def list_by_key(self, key_id: str) -> list[IPAllowlistEntry]: ...
    def delete(self, entry_id: str) -> None: ...


# ---------------------------------------------------------------------------
# InMemory stubs
# ---------------------------------------------------------------------------


class InMemoryAPIKeyStore:
    def __init__(self) -> None:
        self._by_id: dict[str, APIKey] = {}
        self._by_hash: dict[str, APIKey] = {}

    def save(self, k: APIKey) -> None:
        self._by_id[k.key_id] = k
        self._by_hash[k.key_hash] = k

    def get_by_id(self, key_id: str) -> APIKey | None:
        return self._by_id.get(key_id)

    def get_by_hash(self, key_hash: str) -> APIKey | None:
        return self._by_hash.get(key_hash)

    def list_by_owner(self, owner_id: str) -> list[APIKey]:
        return [k for k in self._by_id.values() if k.owner_id == owner_id]

    def update(self, k: APIKey) -> None:
        # Remove old hash entry if key_hash changed
        for stored in list(self._by_hash.values()):
            if stored.key_id == k.key_id and stored.key_hash != k.key_hash:
                del self._by_hash[stored.key_hash]
        self._by_id[k.key_id] = k
        self._by_hash[k.key_hash] = k


class InMemoryRateLimitPolicyStore:
    def __init__(self) -> None:
        now = datetime.now(UTC)
        self._policies: dict[UsageTier, RateLimitPolicy] = {
            UsageTier.FREE: RateLimitPolicy(
                policy_id=str(uuid.uuid4()),
                tier=UsageTier.FREE,
                requests_per_second=1,
                requests_per_minute=30,
                requests_per_hour=500,
                burst_allowance=5,
                created_at=now,
            ),
            UsageTier.BASIC: RateLimitPolicy(
                policy_id=str(uuid.uuid4()),
                tier=UsageTier.BASIC,
                requests_per_second=10,
                requests_per_minute=300,
                requests_per_hour=5000,
                burst_allowance=20,
                created_at=now,
            ),
            UsageTier.PREMIUM: RateLimitPolicy(
                policy_id=str(uuid.uuid4()),
                tier=UsageTier.PREMIUM,
                requests_per_second=50,
                requests_per_minute=1500,
                requests_per_hour=20000,
                burst_allowance=100,
                created_at=now,
            ),
            UsageTier.ENTERPRISE: RateLimitPolicy(
                policy_id=str(uuid.uuid4()),
                tier=UsageTier.ENTERPRISE,
                requests_per_second=200,
                requests_per_minute=6000,
                requests_per_hour=100000,
                burst_allowance=500,
                created_at=now,
            ),
        }

    def get_policy(self, tier: UsageTier) -> RateLimitPolicy | None:
        return self._policies.get(tier)

    def save(self, p: RateLimitPolicy) -> None:
        self._policies[p.tier] = p


class InMemoryQuotaStore:
    def __init__(self) -> None:
        self._records: list[QuotaUsage] = []

    def save(self, q: QuotaUsage) -> None:
        self._records = [r for r in self._records if r.usage_id != q.usage_id]
        self._records.append(q)

    def get_current(self, key_id: str, window_start: datetime) -> QuotaUsage | None:
        for r in self._records:
            if r.key_id == key_id and r.window_start.date() == window_start.date():
                return r
        return None

    def get_history(self, key_id: str) -> list[QuotaUsage]:
        return [r for r in self._records if r.key_id == key_id]


class InMemoryRequestLogStore:
    def __init__(self) -> None:
        self._logs: list[RequestLog] = []

    def append(self, log: RequestLog) -> None:
        self._logs.append(log)  # append-only (I-24)

    def list_by_key(self, key_id: str, limit: int = 100) -> list[RequestLog]:
        return [lg for lg in self._logs if lg.key_id == key_id][-limit:]


class InMemoryIPAllowlistStore:
    def __init__(self) -> None:
        self._entries: dict[str, IPAllowlistEntry] = {}

    def save(self, e: IPAllowlistEntry) -> None:
        self._entries[e.entry_id] = e

    def list_by_key(self, key_id: str) -> list[IPAllowlistEntry]:
        return [e for e in self._entries.values() if e.key_id == key_id]

    def delete(self, entry_id: str) -> None:
        self._entries.pop(entry_id, None)
