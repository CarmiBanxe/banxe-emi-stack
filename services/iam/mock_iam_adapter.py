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

from datetime import UTC, datetime, timedelta
import hashlib
import os
import secrets

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
        "mfa_verified": True,  # MLRO requires MFA (FCA SM&CR)
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

    def authenticate(self, username: str, password: str) -> AuthToken | None:
        user = _USERS.get(username)
        if not user:
            return None
        if user["password_hash"] != _h(password):
            return None

        expiry = datetime.now(UTC) + timedelta(seconds=self._ttl)
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

    def validate_token(self, token: str) -> UserIdentity | None:
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


# ── Keycloak adapter (LIVE — deployed on GMKtec :8180) ────────────────────────


class KeycloakAdapter:
    """
    Live Keycloak OIDC adapter with JWKS-based offline JWT validation.
    STATUS: ACTIVE — Keycloak 26.2.5 running on GMKtec :8180

    Realm: banxe | Roles: CEO / MLRO / CCO / OPERATOR / AGENT / AUDITOR / READONLY
    KEYCLOAK_URL=http://localhost:8180  KEYCLOAK_REALM=banxe

    validate_token() verifies JWT signature using Keycloak's public JWKS keys —
    no round-trip to Keycloak per request. JWKS cached for _JWKS_CACHE_TTL seconds.
    authenticate() uses Resource Owner Password Grant (internal services only).
    """

    _JWKS_CACHE_TTL = 300  # seconds

    def __init__(self) -> None:
        self._url = os.environ.get("KEYCLOAK_URL", "")
        self._realm = os.environ.get("KEYCLOAK_REALM", "banxe")
        self._client_id = os.environ.get("KEYCLOAK_CLIENT_ID", "banxe-backend")
        self._client_secret = os.environ.get("KEYCLOAK_CLIENT_SECRET", "")
        if not self._url:
            raise OSError(
                "KEYCLOAK_URL not set. Keycloak is deployed at http://gmktec:8180. "
                "Set KEYCLOAK_URL=http://localhost:8180 and IAM_ADAPTER=keycloak."
            )
        self._token_url = f"{self._url}/realms/{self._realm}/protocol/openid-connect/token"
        self._jwks_url = f"{self._url}/realms/{self._realm}/protocol/openid-connect/certs"
        self._realm_url = f"{self._url}/realms/{self._realm}"
        self._jwks_cache: dict | None = None
        self._jwks_fetched_at: datetime | None = None

    # ── JWKS cache ────────────────────────────────────────────────────────────

    def _fetch_jwks(self) -> dict:
        """Fetch JWKS from Keycloak certs endpoint; cache for _JWKS_CACHE_TTL seconds."""
        import json
        import urllib.request

        now = datetime.now(UTC)
        if (
            self._jwks_cache is not None
            and self._jwks_fetched_at is not None
            and (now - self._jwks_fetched_at).total_seconds() < self._JWKS_CACHE_TTL
        ):
            return self._jwks_cache
        with urllib.request.urlopen(self._jwks_url, timeout=5) as resp:  # nosec B310
            self._jwks_cache = json.loads(resp.read())
            self._jwks_fetched_at = now
            return self._jwks_cache

    # ── IAMPort implementation ────────────────────────────────────────────────

    def authenticate(self, username: str, password: str) -> AuthToken | None:
        """Resource Owner Password Grant — direct user login."""
        from datetime import timedelta
        import json
        import urllib.parse
        import urllib.request

        data = urllib.parse.urlencode(
            {
                "client_id": self._client_id,
                "username": username,
                "password": password,
                "grant_type": "password",
                **({"client_secret": self._client_secret} if self._client_secret else {}),
            }
        ).encode()
        req = urllib.request.Request(self._token_url, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:  # nosec B310
                token_data = json.loads(resp.read())
            expiry = datetime.now(UTC) + timedelta(seconds=token_data.get("expires_in", 3600))
            return AuthToken(
                access_token=token_data["access_token"],
                expires_at=expiry,
                subject=username,
                roles=[],  # Roles extracted from JWT in validate_token
            )
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning("Keycloak authenticate failed: %s", exc)
            return None

    def validate_token(self, token: str) -> UserIdentity | None:
        """
        Validate JWT offline using Keycloak's JWKS public keys (RS256).
        Verifies: signature, expiry, audience.
        Extracts: sub, preferred_username, email, realm_access.roles, acr.
        """
        import json
        import logging

        import jwt  # PyJWT
        from jwt.algorithms import RSAAlgorithm

        log = logging.getLogger(__name__)
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            alg = header.get("alg", "RS256")

            jwks = self._fetch_jwks()
            keys = jwks.get("keys", [])
            if not keys:
                log.warning("Keycloak JWKS returned no keys")
                return None

            jwk = next((k for k in keys if k.get("kid") == kid), None) or keys[0]
            public_key = RSAAlgorithm.from_jwk(json.dumps(jwk))

            payload = jwt.decode(
                token,
                public_key,
                algorithms=[alg],
                audience=self._client_id,
                options={"verify_exp": True},
            )

            roles_raw = payload.get("realm_access", {}).get("roles", [])
            roles = frozenset(BanxeRole(r) for r in roles_raw if r in BanxeRole.__members__)

            exp = payload.get("exp")
            token_expiry = datetime.fromtimestamp(exp, tz=UTC) if exp else None

            return UserIdentity(
                subject=payload.get("sub", ""),
                username=payload.get("preferred_username", ""),
                email=payload.get("email", ""),
                roles=roles or frozenset({BanxeRole.READONLY}),
                mfa_verified=payload.get("acr", "") in ("mfa", "aal2"),
                token_expiry=token_expiry,
            )
        except Exception as exc:
            log.warning("Keycloak validate_token failed: %s", exc)
            return None

    def authorize(self, identity: UserIdentity, permission: Permission) -> bool:
        return identity.has_permission(permission)

    def health(self) -> bool:
        import urllib.request

        try:
            with urllib.request.urlopen(self._realm_url, timeout=3) as r:  # nosec B310
                return r.status == 200
        except Exception:
            return False


def get_iam_adapter() -> IAMPort:
    """Factory: IAM_ADAPTER=mock (default) | keycloak."""
    adapter = os.environ.get("IAM_ADAPTER", "mock").lower()
    if adapter == "keycloak":
        return KeycloakAdapter()
    return MockIAMAdapter()
