from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
import uuid

import pytest

from services.api_gateway.models import (
    APIKey,
    GeoAction,
    InMemoryAPIKeyStore,
    InMemoryIPAllowlistStore,
    InMemoryQuotaStore,
    InMemoryRateLimitPolicyStore,
    InMemoryRequestLogStore,
    IPAllowlistEntry,
    KeyStatus,
    QuotaUsage,
    RateLimitPolicy,
    RateLimitWindow,
    RequestLog,
    UsageTier,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _sample_api_key() -> APIKey:
    return APIKey(
        key_id=str(uuid.uuid4()),
        name="test-key",
        key_hash="abc123",
        scope=["read", "write"],
        tier=UsageTier.BASIC,
        status=KeyStatus.ACTIVE,
        created_at=_now(),
        owner_id="owner-1",
    )


# --- Dataclass creation tests ---


def test_api_key_creation() -> None:
    k = _sample_api_key()
    assert k.name == "test-key"
    assert k.tier == UsageTier.BASIC
    assert k.status == KeyStatus.ACTIVE


def test_api_key_frozen_enforcement() -> None:
    k = _sample_api_key()
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        k.name = "mutated"  # type: ignore[misc]


def test_api_key_optional_fields_default() -> None:
    k = _sample_api_key()
    assert k.rotated_at is None
    assert k.revoked_at is None
    assert k.owner_id == "owner-1"


def test_rate_limit_policy_creation() -> None:
    p = RateLimitPolicy(
        policy_id=str(uuid.uuid4()),
        tier=UsageTier.FREE,
        requests_per_second=1,
        requests_per_minute=30,
        requests_per_hour=500,
        burst_allowance=5,
        created_at=_now(),
    )
    assert p.tier == UsageTier.FREE
    assert p.requests_per_minute == 30


def test_quota_usage_creation() -> None:
    now = _now()
    q = QuotaUsage(
        usage_id=str(uuid.uuid4()),
        key_id="k1",
        window_start=now,
        window_end=now,
        request_count=5,
        tier=UsageTier.PREMIUM,
        updated_at=now,
    )
    assert q.request_count == 5
    assert q.tier == UsageTier.PREMIUM


def test_request_log_creation() -> None:
    log = RequestLog(
        log_id=str(uuid.uuid4()),
        key_id="k1",
        method="GET",
        path="/v1/test",
        status_code=200,
        latency_ms=42,
        timestamp=_now(),
        ip_address="192.168.1.1",
    )
    assert log.status_code == 200
    assert log.latency_ms == 42


def test_ip_allowlist_entry_creation() -> None:
    e = IPAllowlistEntry(
        entry_id=str(uuid.uuid4()),
        key_id="k1",
        cidr="10.0.0.0/8",
        action=GeoAction.ALLOW,
        created_at=_now(),
    )
    assert e.action == GeoAction.ALLOW


# --- Enum value tests ---


def test_usage_tier_enum_values() -> None:
    assert UsageTier.FREE.value == "FREE"
    assert UsageTier.BASIC.value == "BASIC"
    assert UsageTier.PREMIUM.value == "PREMIUM"
    assert UsageTier.ENTERPRISE.value == "ENTERPRISE"


def test_key_status_enum_values() -> None:
    assert KeyStatus.ACTIVE.value == "ACTIVE"
    assert KeyStatus.ROTATED.value == "ROTATED"
    assert KeyStatus.REVOKED.value == "REVOKED"


def test_rate_limit_window_enum_values() -> None:
    assert RateLimitWindow.SECOND.value == "SECOND"
    assert RateLimitWindow.MINUTE.value == "MINUTE"
    assert RateLimitWindow.HOUR.value == "HOUR"
    assert RateLimitWindow.DAY.value == "DAY"


def test_geo_action_enum_values() -> None:
    assert GeoAction.ALLOW.value == "ALLOW"
    assert GeoAction.BLOCK.value == "BLOCK"


# --- InMemory store CRUD tests ---


def test_in_memory_api_key_store_save_and_get() -> None:
    store = InMemoryAPIKeyStore()
    k = _sample_api_key()
    store.save(k)
    assert store.get_by_id(k.key_id) == k


def test_in_memory_api_key_store_get_by_hash() -> None:
    store = InMemoryAPIKeyStore()
    k = _sample_api_key()
    store.save(k)
    assert store.get_by_hash(k.key_hash) == k


def test_in_memory_quota_store_crud() -> None:
    store = InMemoryQuotaStore()
    now = _now()
    q = QuotaUsage(
        usage_id=str(uuid.uuid4()),
        key_id="k1",
        window_start=now,
        window_end=now,
        request_count=3,
        tier=UsageTier.BASIC,
        updated_at=now,
    )
    store.save(q)
    result = store.get_current("k1", now)
    assert result is not None
    assert result.request_count == 3


def test_in_memory_request_log_store_append_only() -> None:
    store = InMemoryRequestLogStore()
    log = RequestLog(
        log_id=str(uuid.uuid4()),
        key_id="k1",
        method="POST",
        path="/v1/pay",
        status_code=201,
        latency_ms=10,
        timestamp=_now(),
        ip_address="1.2.3.4",
    )
    store.append(log)
    results = store.list_by_key("k1")
    assert len(results) == 1
    assert results[0].log_id == log.log_id


# --- Seeded rate limit policies ---


def test_seeded_free_tier_policy() -> None:
    store = InMemoryRateLimitPolicyStore()
    p = store.get_policy(UsageTier.FREE)
    assert p is not None
    assert p.requests_per_second == 1
    assert p.requests_per_minute == 30
    assert p.requests_per_hour == 500
    assert p.burst_allowance == 5


def test_seeded_basic_tier_policy() -> None:
    store = InMemoryRateLimitPolicyStore()
    p = store.get_policy(UsageTier.BASIC)
    assert p is not None
    assert p.requests_per_second == 10
    assert p.requests_per_minute == 300
    assert p.requests_per_hour == 5000
    assert p.burst_allowance == 20


def test_seeded_premium_tier_policy() -> None:
    store = InMemoryRateLimitPolicyStore()
    p = store.get_policy(UsageTier.PREMIUM)
    assert p is not None
    assert p.requests_per_second == 50
    assert p.requests_per_minute == 1500
    assert p.requests_per_hour == 20000
    assert p.burst_allowance == 100


def test_seeded_enterprise_tier_policy() -> None:
    store = InMemoryRateLimitPolicyStore()
    p = store.get_policy(UsageTier.ENTERPRISE)
    assert p is not None
    assert p.requests_per_second == 200
    assert p.requests_per_minute == 6000
    assert p.requests_per_hour == 100000
    assert p.burst_allowance == 500


def test_in_memory_ip_allowlist_store_crud() -> None:
    store = InMemoryIPAllowlistStore()
    now = _now()
    e = IPAllowlistEntry(
        entry_id=str(uuid.uuid4()),
        key_id="k1",
        cidr="192.168.0.0/16",
        action=GeoAction.ALLOW,
        created_at=now,
    )
    store.save(e)
    entries = store.list_by_key("k1")
    assert len(entries) == 1
    store.delete(e.entry_id)
    assert store.list_by_key("k1") == []
