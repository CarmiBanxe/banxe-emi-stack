"""
services/api_versioning/models.py — API Versioning Domain Models
IL-AVD-01 | Phase 44 | banxe-emi-stack
FCA COND 2.2, PSD2 Art.30, RFC 8594 Sunset header.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ApiVersion(StrEnum):
    V1 = "v1"
    V2 = "v2"
    V3 = "v3"  # future


class VersionStatus(StrEnum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    SUNSET = "sunset"  # RFC 8594: Sunset header
    EXPERIMENTAL = "experimental"


class BreakingChangeType(StrEnum):
    FIELD_REMOVED = "field_removed"
    FIELD_TYPE_CHANGED = "field_type_changed"
    ENDPOINT_REMOVED = "endpoint_removed"
    ENDPOINT_RENAMED = "endpoint_renamed"
    BEHAVIOR_CHANGED = "behavior_changed"
    AUTH_CHANGED = "auth_changed"


@dataclass(frozen=True)
class ApiVersionSpec:
    version: ApiVersion
    status: VersionStatus
    release_date: str  # ISO date string
    sunset_date: str | None  # RFC 8594 Sunset date
    deprecation_notice_days: int = 90  # FCA: 90-day notice
    changelog_url: str | None = None


@dataclass(frozen=True)
class BreakingChange:
    change_id: str
    version_from: ApiVersion
    version_to: ApiVersion
    change_type: BreakingChangeType
    endpoint: str
    description: str
    migration_guide: str
    introduced_at: str  # ISO datetime


@dataclass(frozen=True)
class DeprecationNotice:
    notice_id: str
    version: ApiVersion
    endpoint: str
    sunset_date: str
    migration_endpoint: str
    created_at: str


@dataclass
class HITLProposal:
    action: str
    version: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"
