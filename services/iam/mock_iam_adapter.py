"""
mock_iam_adapter.py — In-memory Mock IAM Adapter (FA-14 / Keycloak)
FCA SM&CR | banxe-emi-stack

WHY THIS EXISTS
---------------
Keycloak requires a deployed instance (Docker or managed). MockIAMAdapter
lets us build and test all auth/authz logic immediately without Keycloak.

When Keycloak is deployed:
  1. Set IAM_ADAPTER=keycloak in .env
  2. Set KEYCLOAK_URL, KEYCLOAK_REALM, KEYCLOAK_CLIENT_ID, KEYCLOAK_CLIENT_SECRET
  3. get_iam_adapter() switches automatically

Pre-configured users (matches Banxe SM&CR structure):
  mark@banxe.io / ceo-pass       → CEO
  mlro@banxe.io / mlro-pass      → MLRO (SMF17, MFA required)
  compliance@banxe.io / cco-pass → CCO
  operator@banxe.io / op-pass    → OPERATOR
  agent-aml / agent-pass          → AGENT (AI agent identity)
  auditor@fca.gov.uk / audit-pass → AUDITOR
"""
from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from services.iam.iam_port import AuthToken, BanxeRole, IAMPort, Permission, UserIdentity

_TOKEN_TTL_SECONDS = int(os.environ.get("IAM_TOKEN_TTL", "3600"))

# ── Credential store ──────────────────────────────────────────────────────────

def _h(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


_USERS: dict[str, dict] = {
    "mark@banxe.io": {
        "password_hash": _h("ceo-pass"),
        "roles": frozenset({BanxeRole.CEO}),
        "subject": "uuid-ceo-001",
        "email": "mark@banxe.io",
        "mfa_verified": True,
    },
    "mlro@banxe.io": {
        "password_hash": _h("mlro-pass"),
        "roles": frozenset({BanxeRole.MLRO}),
        "subject": "uuid-mlro-001",
        "email": "mlro@banxe.io",
        "mfa_verified": True,   # MLRO requires MFA (FCA SM&CR)
    },
    "compliance@banxe.io": {
        "password_hash": _h("cco-pass"),
        "roles": frozenset({BanxeRole.CCO}),
        "subject": "uuid-cco-001",
        "email": "compliance@banxe.io",
        "mfa_verified": False,
    },
    "operator@banxe.io": {
        "password_hash": _h("op-pass"),
        "roles": frozenset({BanxeRole.OPERATOR}),
        "subject": "uuid-op-001",
        "email": "operator@banxe.io",
        "mfa_verified": False,
    },
    "agent-aml": {
        "password_hash": _h("agent-pass"),
        "roles": frozenset({BanxeRole.AGENT}),
        "subject": "uuid-agent-aml",
        "email": "agent-aml@internal.banxe.io",
        "mfa_verified": True,  # agents use service credentials (no human MFA)
    },
    "auditor@fca.gov.uk": {
        "password_hash": _h("audit-pass"),
        "roles": frozenset({BanxeRole.AUDITOR}),
        "subject": "uuid-auditor-001",
        "email": "auditor@fca.gov.uk",
        "mfa_verified": True,
    },
}


class MockIAMAdapter:
    """
    In-memory IAM adapter. Thread-safe read-only token store.
    Tokens are opaque random strings mapped to UserIdentity.
    """

    def __init__(self, ttl_seconds: int = _TOKEN_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._tokens: dict[str, UserIdentity] = {}

    def authenticate(self, username: str, password: str) -> Optional[AuthToken]:
        user = _USERS.get(username)
        if not user:
            return None
        if user["password_hash"] != _h(password):
            return None

        expiry = datetime.now(timezone.utc) + timedelta(seconds=self._ttl)
        token_str = secrets.token_urlsafe(32)
        identity = UserIdentity(
            subject=user["subject"],
            username=username,
            email=user["email"],
            roles=user["roles"],
            mfa_verified=user["mfa_verified"],
            token_expiry=expiry,
        )
        self._tokens[token_str] = identity
        return AuthToken(
            access_token=token_str,
            expires_at=expiry,
            subject=user["subject"],
            roles=list(user["roles"]),
        )

    def validate_token(self, token: str) -> Optional[UserIdentity]:
        identity = self._tokens.get(token)
        if identity is None:
            return None
        if not identity.is_token_valid:
            del self._tokens[token]
            return None
        return identity

    def authorize(self, identity: UserIdentity, permission: Permission) -> bool:
        return identity.has_permission(permission)

    def health(self) -> bool:
        return True


# ── Keycloak adapter stub ──────────────────────────────────────────────────────

class KeycloakAdapter:  # pragma: no cover
    """
    Live Keycloak adapter stub.
    STATUS: STUB — requires Keycloak deployment (Docker or managed).

    Deploy: docker run -p 8080:8080 quay.io/keycloak/keycloak:latest start-dev
    Realm config: config/keycloak-realm.json (import via Admin Console)
    """

    def __init__(self) -> None:
        self._url = os.environ.get("KEYCLOAK_URL", "")
        self._realm = os.environ.get("KEYCLOAK_REALM", "banxe")
        self._client_id = os.environ.get("KEYCLOAK_CLIENT_ID", "")
        self._client_secret = os.environ.get("KEYCLOAK_CLIENT_SECRET", "")
        if not self._url or not self._client_id:
            raise EnvironmentError(
                "KEYCLOAK_URL and KEYCLOAK_CLIENT_ID must be set. "
                "Deploy Keycloak first, then import config/keycloak-realm.json. "
                "Use IAM_ADAPTER=mock for development."
            )

    def authenticate(self, username: str, password: str) -> Optional[AuthToken]:
        raise NotImplementedError("KeycloakAdapter.authenticate() not yet implemented.")

    def validate_token(self, token: str) -> Optional[UserIdentity]:
        raise NotImplementedError("KeycloakAdapter.validate_token() not yet implemented.")

    def authorize(self, identity: UserIdentity, permission: Permission) -> bool:
        return identity.has_permission(permission)

    def health(self) -> bool:
        return False


def get_iam_adapter() -> IAMPort:
    """Factory: IAM_ADAPTER=mock (default) | keycloak."""
    adapter = os.environ.get("IAM_ADAPTER", "mock").lower()
    if adapter == "keycloak":
        return KeycloakAdapter()
    return MockIAMAdapter()
