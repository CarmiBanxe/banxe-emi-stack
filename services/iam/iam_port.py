"""
iam_port.py — IAMPort: hexagonal interface for Identity & Access Management
FA-14 (Keycloak) | FCA SM&CR | GDPR | banxe-emi-stack

WHY THIS FILE EXISTS
--------------------
FCA Senior Managers & Certification Regime (SM&CR) requires that all
access to compliance-sensitive functions is role-controlled and auditable.
GDPR requires data access to be restricted to authorised personnel.

Keycloak is the target IAM provider (SSO + RBAC + MFA). This Port defines
the canonical interface so that:
  - Business logic depends ONLY on this interface, never on Keycloak SDK
  - MockIAMAdapter works for tests/dev without a Keycloak instance
  - KeycloakAdapter can be plugged in when Keycloak is deployed

Roles (aligned with FCA SM&CR):
  CEO         — all permissions, FCA-notified Senior Manager
  MLRO        — AML/SAR authority, SMF17, cannot be overridden by CEO
  CCO         — Compliance Officer, EDD sign-off (below MLRO level)
  OPERATOR    — Day-to-day transaction processing, no policy access
  AGENT       — AI agent identity, restricted to read + action within scope
  AUDITOR     — Read-only access to audit trail (FCA inspectors)
  READONLY    — Read-only (board reporting, external auditor)

FCA SM&CR references: SYSC 4.7, FIT 1.3, SUP 10C
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol


class BanxeRole(str, Enum):
    """Banxe EMI role hierarchy (FCA SM&CR aligned)."""

    CEO = "CEO"
    MLRO = "MLRO"  # SMF17 — Money Laundering Reporting Officer
    CCO = "CCO"  # Chief Compliance Officer
    OPERATOR = "OPERATOR"
    AGENT = "AGENT"  # AI agent identity
    AUDITOR = "AUDITOR"
    READONLY = "READONLY"


class Permission(str, Enum):
    """Granular permissions mapped to FCA obligations."""

    # AML / SAR
    FILE_SAR = "FILE_SAR"  # MLRO only (POCA 2002)
    APPROVE_EDD = "APPROVE_EDD"  # MLRO only
    VIEW_AML_QUEUE = "VIEW_AML_QUEUE"  # CCO, MLRO
    # Payments
    APPROVE_PAYMENT = "APPROVE_PAYMENT"
    HOLD_PAYMENT = "HOLD_PAYMENT"
    REJECT_PAYMENT = "REJECT_PAYMENT"
    # Thresholds / Config (requires MLRO approval per I-07)
    CHANGE_WATCHMAN_THRESHOLD = "CHANGE_WATCHMAN_THRESHOLD"  # MLRO + CEO only
    # Customer data
    VIEW_CUSTOMER_PII = "VIEW_CUSTOMER_PII"
    VIEW_AUDIT_TRAIL = "VIEW_AUDIT_TRAIL"
    # Compliance
    APPROVE_COMPLAINT = "APPROVE_COMPLAINT"
    VIEW_COMPLIANCE_REPORTS = "VIEW_COMPLIANCE_REPORTS"
    SUBMIT_REGDATA = "SUBMIT_REGDATA"


# Role → permissions mapping (canonical, read-only)
ROLE_PERMISSIONS: dict[BanxeRole, frozenset[Permission]] = {
    BanxeRole.CEO: frozenset(Permission),  # all permissions
    BanxeRole.MLRO: frozenset(
        {
            Permission.FILE_SAR,
            Permission.APPROVE_EDD,
            Permission.VIEW_AML_QUEUE,
            Permission.HOLD_PAYMENT,
            Permission.REJECT_PAYMENT,
            Permission.CHANGE_WATCHMAN_THRESHOLD,
            Permission.VIEW_CUSTOMER_PII,
            Permission.VIEW_AUDIT_TRAIL,
            Permission.APPROVE_COMPLAINT,
            Permission.VIEW_COMPLIANCE_REPORTS,
            Permission.SUBMIT_REGDATA,
        }
    ),
    BanxeRole.CCO: frozenset(
        {
            Permission.VIEW_AML_QUEUE,
            Permission.HOLD_PAYMENT,
            Permission.VIEW_CUSTOMER_PII,
            Permission.VIEW_AUDIT_TRAIL,
            Permission.APPROVE_COMPLAINT,
            Permission.VIEW_COMPLIANCE_REPORTS,
        }
    ),
    BanxeRole.OPERATOR: frozenset(
        {
            Permission.APPROVE_PAYMENT,
            Permission.HOLD_PAYMENT,
            Permission.REJECT_PAYMENT,
            Permission.VIEW_CUSTOMER_PII,
        }
    ),
    BanxeRole.AGENT: frozenset(
        {
            Permission.VIEW_AML_QUEUE,
            Permission.HOLD_PAYMENT,
            Permission.REJECT_PAYMENT,
            Permission.VIEW_AUDIT_TRAIL,
        }
    ),
    BanxeRole.AUDITOR: frozenset(
        {
            Permission.VIEW_AUDIT_TRAIL,
            Permission.VIEW_COMPLIANCE_REPORTS,
        }
    ),
    BanxeRole.READONLY: frozenset(
        {
            Permission.VIEW_COMPLIANCE_REPORTS,
        }
    ),
}


@dataclass(frozen=True)
class UserIdentity:
    """Authenticated user/agent identity."""

    subject: str  # Keycloak sub claim (UUID)
    username: str
    email: str
    roles: frozenset[BanxeRole]
    mfa_verified: bool = False
    token_expiry: datetime | None = None

    def has_permission(self, perm: Permission) -> bool:
        return any(perm in ROLE_PERMISSIONS.get(r, frozenset()) for r in self.roles)

    def has_role(self, role: BanxeRole) -> bool:
        return role in self.roles

    @property
    def is_token_valid(self) -> bool:
        if self.token_expiry is None:
            return True
        return datetime.now(UTC) < self.token_expiry


@dataclass
class AuthToken:
    """Opaque auth token returned after successful authentication."""

    access_token: str
    expires_at: datetime
    subject: str
    roles: list[BanxeRole]


class IAMPort(Protocol):
    """Hexagonal port for IAM / RBAC."""

    def authenticate(self, username: str, password: str) -> AuthToken | None: ...
    def validate_token(self, token: str) -> UserIdentity | None: ...
    def authorize(self, identity: UserIdentity, permission: Permission) -> bool: ...
    def health(self) -> bool: ...
