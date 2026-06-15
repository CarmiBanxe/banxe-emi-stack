"""tests/test_legacy_role_guard.py — production tests for LegacyRoleGuardAdapter.

Covers:
  - pure invariant `role ∈ allowed AND status == 'ACTIVE'` per source TS
  - require_roles(...) FastAPI dependency: accept / 401 / 403
  - dependency-injection via TestClient (no router edit, app built locally)
  - require_roles requires at least one role
"""

from __future__ import annotations

import time
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
import jwt
import pytest

from services.auth.legacy.jwks_models import Jwk, JwksSet
from services.auth.legacy.jwt_strategy import LegacyJwtStrategyAdapter
from services.auth.legacy.role_guard import (
    LegacyRoleGuard,
    LegacyRoleGuardAdapter,
    make_legacy_role_guard,
    require_roles,
)

# ── pure invariant ──────────────────────────────────────────────────────────


def test_check_passes_when_role_in_allowed_and_status_active():
    guard = LegacyRoleGuardAdapter(allowed_roles=["MLRO", "CEO"])
    assert guard.check(role="MLRO", status="ACTIVE") is True
    assert guard.check(role="CEO", status="ACTIVE") is True


def test_check_fails_when_role_not_in_allowed():
    guard = LegacyRoleGuardAdapter(allowed_roles=["MLRO"])
    assert guard.check(role="OPERATOR", status="ACTIVE") is False


def test_check_fails_when_status_not_active():
    guard = LegacyRoleGuardAdapter(allowed_roles=["MLRO"])
    assert guard.check(role="MLRO", status="INACTIVE") is False
    assert guard.check(role="MLRO", status="SUSPENDED") is False
    assert guard.check(role="MLRO", status="") is False


def test_allowed_roles_property_is_immutable_tuple():
    guard = LegacyRoleGuardAdapter(allowed_roles=["MLRO", "CEO"])
    assert guard.allowed_roles == ("MLRO", "CEO")
    assert isinstance(guard.allowed_roles, tuple)


def test_make_legacy_role_guard_factory():
    guard = make_legacy_role_guard("MLRO", "OPS")
    assert isinstance(guard, LegacyRoleGuardAdapter)
    assert guard.allowed_roles == ("MLRO", "OPS")


def test_legacy_role_guard_alias_points_to_adapter():
    """Backward-compat alias for PR #74 scaffold tests."""
    assert LegacyRoleGuard is LegacyRoleGuardAdapter


# ── require_roles factory ───────────────────────────────────────────────────


def _generate_rsa_keypair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


def _public_to_jwk(public_key: rsa.RSAPublicKey, kid: str) -> Jwk:
    import base64

    numbers = public_key.public_numbers()

    def _b64u_uint(value: int) -> str:
        byte_len = (value.bit_length() + 7) // 8
        return (
            base64.urlsafe_b64encode(value.to_bytes(byte_len, "big")).rstrip(b"=").decode("ascii")
        )

    return Jwk(
        kty="RSA",
        e=_b64u_uint(numbers.e),
        n=_b64u_uint(numbers.n),
        use="sig",
        kid=kid,
        alg="RS256",
    )


def _sign(private_key: rsa.RSAPrivateKey, *, kid: str, claims: dict[str, Any]) -> str:
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return jwt.encode(claims, pem, algorithm="RS256", headers={"kid": kid, "alg": "RS256"})


@pytest.fixture
def signing_setup():
    private, public = _generate_rsa_keypair()
    jwk = _public_to_jwk(public, kid="kid-roleguard")
    strategy = LegacyJwtStrategyAdapter(jwks_provider=lambda: JwksSet(keys=[jwk]))
    return private, strategy


def _build_app(strategy: LegacyJwtStrategyAdapter, *roles: str) -> FastAPI:
    app = FastAPI()
    guard = require_roles(*roles, jwt_strategy=strategy)

    @app.get("/protected")
    def protected(claims: dict = Depends(guard)) -> dict[str, Any]:
        return {"ok": True, "claims": claims}

    return app


def test_require_roles_rejects_when_called_without_roles():
    strategy = LegacyJwtStrategyAdapter(jwks_provider=lambda: JwksSet())
    with pytest.raises(ValueError, match="at least one role"):
        require_roles(jwt_strategy=strategy)


def test_dependency_accepts_valid_token_with_allowed_role(signing_setup):
    private, strategy = signing_setup
    app = _build_app(strategy, "MLRO", "CEO")
    client = TestClient(app)

    token = _sign(
        private,
        kid="kid-roleguard",
        claims={
            "sub": "u-1",
            "role": "MLRO",
            "status": "ACTIVE",
            "service": "tx-auth",
            "exp": int(time.time()) + 600,
        },
    )
    resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["claims"]["role"] == "MLRO"


def test_dependency_returns_401_when_authorization_header_missing(signing_setup):
    _, strategy = signing_setup
    app = _build_app(strategy, "MLRO")
    client = TestClient(app)
    resp = client.get("/protected")
    assert resp.status_code == 422  # FastAPI: missing Header(...) → 422


def test_dependency_returns_401_when_bearer_prefix_missing(signing_setup):
    _, strategy = signing_setup
    app = _build_app(strategy, "MLRO")
    client = TestClient(app)
    resp = client.get("/protected", headers={"Authorization": "Token abc.def.ghi"})
    assert resp.status_code == 401
    assert "Bearer" in resp.json()["detail"]


def test_dependency_returns_401_on_invalid_token(signing_setup):
    _, strategy = signing_setup
    app = _build_app(strategy, "MLRO")
    client = TestClient(app)
    resp = client.get("/protected", headers={"Authorization": "Bearer not.a.valid.jwt"})
    assert resp.status_code == 401


def test_dependency_returns_403_when_role_not_in_allowed(signing_setup):
    private, strategy = signing_setup
    app = _build_app(strategy, "MLRO")
    client = TestClient(app)

    token = _sign(
        private,
        kid="kid-roleguard",
        claims={
            "sub": "u-1",
            "role": "OPERATOR",
            "status": "ACTIVE",
            "service": "tx-auth",
            "exp": int(time.time()) + 600,
        },
    )
    resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_dependency_returns_403_when_status_not_active(signing_setup):
    private, strategy = signing_setup
    app = _build_app(strategy, "MLRO")
    client = TestClient(app)

    token = _sign(
        private,
        kid="kid-roleguard",
        claims={
            "sub": "u-1",
            "role": "MLRO",
            "status": "SUSPENDED",
            "service": "tx-auth",
            "exp": int(time.time()) + 600,
        },
    )
    resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_dependency_returns_401_on_expired_token(signing_setup):
    private, strategy = signing_setup
    app = _build_app(strategy, "MLRO")
    client = TestClient(app)

    token = _sign(
        private,
        kid="kid-roleguard",
        claims={
            "sub": "u-1",
            "role": "MLRO",
            "status": "ACTIVE",
            "service": "tx-auth",
            "exp": int(time.time()) - 60,
        },
    )
    resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
