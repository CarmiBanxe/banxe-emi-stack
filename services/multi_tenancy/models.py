"""
services/multi_tenancy/models.py — Multi-Tenancy Domain Models
IL-MT-01 | Phase 43 | banxe-emi-stack
I-01: Decimal. I-24: append-only audit. I-27: HITL proposals.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol


class TenantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"
    PENDING_KYB = "pending_kyb"


class TenantTier(StrEnum):
    BASIC = "basic"  # £10/mo, 1000 tx/day
    BUSINESS = "business"  # £99/mo, 10000 tx/day
    ENTERPRISE = "enterprise"  # bespoke, unlimited


class IsolationLevel(StrEnum):
    SHARED = "shared"  # shared DB schema, tenant_id row-level
    SCHEMA = "schema"  # separate DB schema per tenant
    DEDICATED = "dedicated"  # dedicated DB instance (Enterprise only)


@dataclass(frozen=True)
class Tenant:
    tenant_id: str
    name: str
    tier: TenantTier
    status: TenantStatus
    isolation_level: IsolationLevel
    monthly_fee: Decimal  # I-01: Decimal
    daily_tx_limit: int
    jurisdiction: str
    kyb_verified: bool = False
    cass_pool_id: str | None = None  # CASS 7: separate client money pool


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    user_id: str
    scopes: list[str]
    request_id: str


@dataclass(frozen=True)
class TenantQuota:
    tenant_id: str
    daily_tx_used: int
    daily_tx_limit: int
    monthly_volume_gbp: Decimal  # I-01
    monthly_volume_limit_gbp: Decimal  # I-01


@dataclass(frozen=True)
class TenantAuditEntry:
    entry_id: str
    tenant_id: str
    action: str
    actor: str
    timestamp: str
    details: dict


@dataclass
class HITLProposal:
    action: str
    tenant_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


# ── Protocols ─────────────────────────────────────────────────────────────────


class TenantPort(Protocol):
    def get(self, tenant_id: str) -> Tenant | None: ...
    def save(self, tenant: Tenant) -> None: ...
    def list_active(self) -> list[Tenant]: ...


class TenantAuditPort(Protocol):
    def append(self, entry: TenantAuditEntry) -> None: ...  # I-24: append-only
    def list_by_tenant(self, tenant_id: str) -> list[TenantAuditEntry]: ...


class QuotaPort(Protocol):
    def get(self, tenant_id: str) -> TenantQuota | None: ...
    def save(self, quota: TenantQuota) -> None: ...


# ── InMemory stubs ─────────────────────────────────────────────────────────────


class InMemoryTenantPort:
    def __init__(self) -> None:
        self._data: dict[str, Tenant] = {}

    def get(self, tenant_id: str) -> Tenant | None:
        return self._data.get(tenant_id)

    def save(self, tenant: Tenant) -> None:
        self._data[tenant.tenant_id] = tenant

    def list_active(self) -> list[Tenant]:
        return [t for t in self._data.values() if t.status == TenantStatus.ACTIVE]


class InMemoryTenantAuditPort:
    def __init__(self) -> None:
        self._log: list[TenantAuditEntry] = []

    def append(self, entry: TenantAuditEntry) -> None:  # I-24
        self._log.append(entry)

    def list_by_tenant(self, tenant_id: str) -> list[TenantAuditEntry]:
        return [e for e in self._log if e.tenant_id == tenant_id]


class InMemoryQuotaPort:
    def __init__(self) -> None:
        self._data: dict[str, TenantQuota] = {}

    def get(self, tenant_id: str) -> TenantQuota | None:
        return self._data.get(tenant_id)

    def save(self, quota: TenantQuota) -> None:
        self._data[quota.tenant_id] = quota
