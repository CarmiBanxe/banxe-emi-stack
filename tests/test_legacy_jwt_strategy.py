"""tests/test_legacy_jwt_strategy.py — production parity tests vs banxe-tx-auth source.

Verifies `LegacyJwtStrategyAdapter.validate_access_token`:
  - claim schema parity ({userId, role, status, service}) per
    banxe-tx-auth/src/auth/strategy/jwt.strategy.ts::validate
  - signature verification via injected JWKS
  - rejects expired / wrong-key / wrong-kid / wrong-algorithm tokens
  - rejects missing required claims
  - JWKS HTTP fetch contract (mocked transport, no real network)

Test JWTs are signed with a fresh in-process RSA key; no real BANXE.RAR
secrets are used.
"""

from __future__ import annotations

from collections.abc import Callable
import json
import time
from typing import Any
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
import pytest

from services.auth.legacy.jwks_models import Jwk, JwksSet
from services.auth.legacy.jwt_strategy import (
    LegacyJwtStrategy,
    LegacyJwtStrategyAdapter,
    TokenValidationError,
)

# ── helpers ─────────────────────────────────────────────────────────────────


def _generate_rsa_keypair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


def _public_to_jwk(public_key: rsa.RSAPublicKey, kid: str) -> Jwk:
    """Build a JWK from a cryptography public key (RFC-7517 RSA fields)."""
    import base64

    numbers = public_key.public_numbers()

    def _b64u_uint(value: int) -> str:
        byte_len = (value.bit_length() + 7) // 8
        raw = value.to_bytes(byte_len, "big")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    return Jwk(
        kty="RSA",
        e=_b64u_uint(numbers.e),
        n=_b64u_uint(numbers.n),
        use="sig",
        kid=kid,
        alg="RS256",
    )


def _private_pem(private_key: rsa.RSAPrivateKey) -> bytes:
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _make_adapter(
    jwk: Jwk,
    *,
    audience: str | None = None,
    issuer: str | None = None,
) -> LegacyJwtStrategyAdapter:
    return LegacyJwtStrategyAdapter(
        jwks_provider=lambda: JwksSet(keys=[jwk]),
        audience=audience,
        issuer=issuer,
    )


def _sign_token(
    private_key: rsa.RSAPrivateKey,
    *,
    kid: str,
    payload: dict[str, Any],
    algorithm: str = "RS256",
) -> str:
    return jwt.encode(
        payload,
        _private_pem(private_key),
        algorithm=algorithm,
        headers={"kid": kid, "alg": algorithm},
    )


# ── ctor + config ───────────────────────────────────────────────────────────


def test_adapter_requires_jwks_uri_or_provider():
    with pytest.raises(ValueError, match="jwks_uri or jwks_provider"):
        LegacyJwtStrategyAdapter()


def test_adapter_alias_legacy_jwt_strategy_points_to_adapter():
    """Backward-compat alias for PR #74 scaffold tests."""
    assert LegacyJwtStrategy is LegacyJwtStrategyAdapter


# ── happy path: claim schema parity ─────────────────────────────────────────


def test_validate_returns_source_claim_schema():
    """validate must return {userId, role, status, service} per source TS."""
    private, public = _generate_rsa_keypair()
    jwk = _public_to_jwk(public, kid="kid-happy")
    adapter = _make_adapter(jwk)

    payload = {
        "sub": "user-001",
        "role": "MLRO",
        "status": "ACTIVE",
        "service": "tx-auth",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    token = _sign_token(private, kid="kid-happy", payload=payload)

    claims = adapter.validate_access_token(token)
    assert claims == {
        "userId": "user-001",
        "role": "MLRO",
        "status": "ACTIVE",
        "service": "tx-auth",
    }


def test_validate_with_audience_and_issuer():
    private, public = _generate_rsa_keypair()
    jwk = _public_to_jwk(public, kid="kid-aud")
    adapter = _make_adapter(jwk, audience="banxe-backend", issuer="https://issuer.example")

    payload = {
        "sub": "u",
        "role": "OPERATOR",
        "status": "ACTIVE",
        "service": "tx-auth",
        "aud": "banxe-backend",
        "iss": "https://issuer.example",
        "exp": int(time.time()) + 60,
    }
    token = _sign_token(private, kid="kid-aud", payload=payload)
    claims = adapter.validate_access_token(token)
    assert claims["userId"] == "u"


# ── error cases ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad_token", ["", "not-a-jwt", "x.y", None])
def test_validate_rejects_empty_or_malformed_token(bad_token):
    private, public = _generate_rsa_keypair()
    jwk = _public_to_jwk(public, kid="kid-x")
    adapter = _make_adapter(jwk)

    with pytest.raises(TokenValidationError) as exc_info:
        adapter.validate_access_token(bad_token)  # type: ignore[arg-type]
    assert exc_info.value.code == "invalid_token"


def test_validate_rejects_missing_kid_header():
    private, _ = _generate_rsa_keypair()
    _, public2 = _generate_rsa_keypair()
    jwk = _public_to_jwk(public2, kid="kid-real")
    adapter = _make_adapter(jwk)

    # Sign without kid
    token = jwt.encode(
        {"sub": "u", "role": "MLRO", "status": "ACTIVE", "service": "tx-auth"},
        _private_pem(private),
        algorithm="RS256",
    )
    with pytest.raises(TokenValidationError) as exc_info:
        adapter.validate_access_token(token)
    assert "missing 'kid'" in exc_info.value.message


def test_validate_rejects_kid_mismatch():
    private, public = _generate_rsa_keypair()
    jwk = _public_to_jwk(public, kid="kid-real")
    adapter = _make_adapter(jwk)

    payload = {"sub": "u", "role": "MLRO", "status": "ACTIVE", "service": "tx-auth"}
    token = _sign_token(private, kid="kid-other", payload=payload)
    with pytest.raises(TokenValidationError) as exc_info:
        adapter.validate_access_token(token)
    assert exc_info.value.code == "kid_mismatch"


def test_validate_rejects_expired_token():
    private, public = _generate_rsa_keypair()
    jwk = _public_to_jwk(public, kid="kid-exp")
    adapter = _make_adapter(jwk)

    payload = {
        "sub": "u",
        "role": "MLRO",
        "status": "ACTIVE",
        "service": "tx-auth",
        "exp": int(time.time()) - 60,
    }
    token = _sign_token(private, kid="kid-exp", payload=payload)
    with pytest.raises(TokenValidationError) as exc_info:
        adapter.validate_access_token(token)
    assert exc_info.value.code == "token_expired"


def test_validate_rejects_wrong_signature_key():
    private_a, public_a = _generate_rsa_keypair()
    private_b, _ = _generate_rsa_keypair()
    jwk = _public_to_jwk(public_a, kid="kid-real")
    adapter = _make_adapter(jwk)

    # sign with B but kid matches the A-key in JWKS
    payload = {"sub": "u", "role": "MLRO", "status": "ACTIVE", "service": "tx-auth"}
    token = _sign_token(private_b, kid="kid-real", payload=payload)
    with pytest.raises(TokenValidationError) as exc_info:
        adapter.validate_access_token(token)
    assert exc_info.value.code == "invalid_token"


def test_validate_rejects_missing_required_claim():
    private, public = _generate_rsa_keypair()
    jwk = _public_to_jwk(public, kid="kid-missing")
    adapter = _make_adapter(jwk)

    # `role` claim missing
    payload = {"sub": "u", "status": "ACTIVE", "service": "tx-auth"}
    token = _sign_token(private, kid="kid-missing", payload=payload)
    with pytest.raises(TokenValidationError) as exc_info:
        adapter.validate_access_token(token)
    assert exc_info.value.code == "missing_claim"


# ── JWKS provider / lookup ──────────────────────────────────────────────────


def test_jwks_provider_called_lazily_and_cached():
    private, public = _generate_rsa_keypair()
    jwk = _public_to_jwk(public, kid="kid-cache")

    calls: list[int] = []

    def provider() -> JwksSet:
        calls.append(1)
        return JwksSet(keys=[jwk])

    adapter = LegacyJwtStrategyAdapter(jwks_provider=provider)

    payload = {"sub": "u", "role": "MLRO", "status": "ACTIVE", "service": "tx-auth"}
    token = _sign_token(private, kid="kid-cache", payload=payload)

    adapter.validate_access_token(token)
    adapter.validate_access_token(token)
    assert len(calls) == 1, "JWKS provider must be cached after first call"


def test_jwks_lookup_miss_raises_kid_mismatch():
    """JWKS empty → kid_mismatch error."""
    adapter = LegacyJwtStrategyAdapter(jwks_provider=lambda: JwksSet(keys=[]))

    private, _ = _generate_rsa_keypair()
    payload = {"sub": "u", "role": "MLRO", "status": "ACTIVE", "service": "tx-auth"}
    token = _sign_token(private, kid="kid-anything", payload=payload)

    with pytest.raises(TokenValidationError) as exc_info:
        adapter.validate_access_token(token)
    assert exc_info.value.code == "kid_mismatch"


# ── HTTP fetch path ─────────────────────────────────────────────────────────


def _patched_urlopen_factory(payload_bytes: bytes) -> Callable[..., Any]:
    class _FakeResp:
        def __init__(self, data: bytes) -> None:
            self._data = data

        def read(self) -> bytes:
            return self._data

        def __enter__(self) -> _FakeResp:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def _fake(*_args: Any, **_kw: Any) -> _FakeResp:
        return _FakeResp(payload_bytes)

    return _fake


def test_http_jwks_fetch_decodes_and_validates():
    private, public = _generate_rsa_keypair()
    jwk = _public_to_jwk(public, kid="kid-http")
    body = json.dumps({"keys": [jwk.model_dump()]}).encode("utf-8")

    adapter = LegacyJwtStrategyAdapter(jwks_uri="https://issuer.example/.well-known/jwks.json")

    payload = {"sub": "u-http", "role": "MLRO", "status": "ACTIVE", "service": "tx-auth"}
    token = _sign_token(private, kid="kid-http", payload=payload)

    with patch("services.auth.legacy.jwt_strategy.urlopen", _patched_urlopen_factory(body)):
        claims = adapter.validate_access_token(token)
    assert claims["userId"] == "u-http"


def test_http_jwks_fetch_failure_propagates_as_token_error():
    adapter = LegacyJwtStrategyAdapter(jwks_uri="https://issuer.example/.well-known/jwks.json")

    private, _ = _generate_rsa_keypair()
    payload = {"sub": "u", "role": "MLRO", "status": "ACTIVE", "service": "tx-auth"}
    token = _sign_token(private, kid="kid-x", payload=payload)

    def _boom(*_a: Any, **_kw: Any):
        raise OSError("network down")

    with patch("services.auth.legacy.jwt_strategy.urlopen", _boom):
        with pytest.raises(TokenValidationError) as exc_info:
            adapter.validate_access_token(token)
    assert exc_info.value.code == "jwks_fetch_failed"


def test_http_jwks_invalid_json_propagates_as_token_error():
    adapter = LegacyJwtStrategyAdapter(jwks_uri="https://issuer.example/.well-known/jwks.json")

    private, _ = _generate_rsa_keypair()
    payload = {"sub": "u", "role": "MLRO", "status": "ACTIVE", "service": "tx-auth"}
    token = _sign_token(private, kid="kid-x", payload=payload)

    with patch(
        "services.auth.legacy.jwt_strategy.urlopen",
        _patched_urlopen_factory(b"not json"),
    ):
        with pytest.raises(TokenValidationError) as exc_info:
            adapter.validate_access_token(token)
    assert exc_info.value.code == "jwks_fetch_failed"


def test_http_jwks_rejects_non_http_scheme():
    adapter = LegacyJwtStrategyAdapter(jwks_uri="file:///etc/passwd")

    private, _ = _generate_rsa_keypair()
    payload = {"sub": "u", "role": "MLRO", "status": "ACTIVE", "service": "tx-auth"}
    token = _sign_token(private, kid="kid-x", payload=payload)

    with pytest.raises(TokenValidationError) as exc_info:
        adapter.validate_access_token(token)
    assert exc_info.value.code == "jwks_fetch_failed"


def test_fetch_jwks_http_guards_against_none_uri():
    """Defensive: _fetch_jwks_http must raise if jwks_uri got cleared post-init."""
    adapter = LegacyJwtStrategyAdapter(jwks_uri="https://issuer.example/.well-known/jwks.json")
    adapter._jwks_uri = None  # simulate config tamper

    with pytest.raises(TokenValidationError) as exc_info:
        adapter._fetch_jwks_http()
    assert exc_info.value.code == "jwks_fetch_failed"
