"""tests/test_legacy_jwks_models.py — RFC-7517 round-trip + BANXE source parity.

Covers `services/auth/legacy/jwks_models.py` (Jwk, Jwks, JwksSet, JwtPayload,
CompleteJwt) on:
  - canonical RFC-7517 JWK round-trip (dict ↔ model ↔ dict)
  - JwksSet envelope (`/.well-known/jwks.json` shape) with `find(kid)`
  - JwtPayload alias coercion (`emailVerified` → `email_verified`)
  - CompleteJwt nested model construction
"""

from __future__ import annotations

from pydantic import ValidationError
import pytest

from services.auth.legacy.jwks_models import (
    CompleteJwt,
    Jwk,
    Jwks,
    JwksSet,
    JwtPayload,
)


def _sample_jwk_dict() -> dict:
    return {
        "kty": "RSA",
        "e": "AQAB",
        "n": "0vx7agoebGcQSuuPiLJXZptN9nndrQmbXEps2aiAFbWhM78L",
        "use": "sig",
        "kid": "kid-rfc7517",
        "alg": "RS256",
    }


# ── Jwk ─────────────────────────────────────────────────────────────────────


def test_jwk_round_trip_via_dict():
    raw = _sample_jwk_dict()
    jwk = Jwk.model_validate(raw)
    assert jwk.kty == "RSA"
    assert jwk.kid == "kid-rfc7517"
    assert jwk.alg == "RS256"
    # round-trip
    assert jwk.model_dump()["kid"] == raw["kid"]


def test_jwk_rejects_non_rsa_kty():
    raw = _sample_jwk_dict()
    raw["kty"] = "EC"
    with pytest.raises(ValidationError):
        Jwk.model_validate(raw)


def test_jwk_accepts_extra_fields():
    """RFC-7517 forward-compat: provider-specific extensions must not error."""
    raw = _sample_jwk_dict()
    raw["x5t"] = "thumbprint-base64url"
    raw["x5c"] = ["cert-chain-base64"]
    jwk = Jwk.model_validate(raw)
    assert jwk.kid == "kid-rfc7517"


# ── JwksSet ─────────────────────────────────────────────────────────────────


def test_jwks_set_find_returns_matching_jwk():
    jwks = JwksSet(keys=[Jwk(**_sample_jwk_dict())])
    found = jwks.find("kid-rfc7517")
    assert found is not None
    assert found.kid == "kid-rfc7517"


def test_jwks_set_find_returns_none_on_miss():
    jwks = JwksSet(keys=[Jwk(**_sample_jwk_dict())])
    assert jwks.find("does-not-exist") is None


def test_jwks_set_default_empty_keys():
    jwks = JwksSet()
    assert jwks.keys == []
    assert jwks.find("anything") is None


def test_jwks_set_round_trip_via_json():
    raw = {"keys": [_sample_jwk_dict()]}
    jwks = JwksSet.model_validate(raw)
    assert len(jwks.keys) == 1
    assert jwks.keys[0].kid == "kid-rfc7517"


# ── Jwks (BANXE source wrapper) ─────────────────────────────────────────────


def test_jwks_minimal_no_pem():
    jwks = Jwks(kid="kid-1", alg="RS256")
    assert jwks.kid == "kid-1"
    assert jwks.pem is None


def test_jwks_with_pem():
    pem = "-----BEGIN PUBLIC KEY-----\nABC\n-----END PUBLIC KEY-----"
    jwks = Jwks(kid="kid-2", alg="RS256", pem=pem)
    assert jwks.pem == pem


# ── JwtPayload ──────────────────────────────────────────────────────────────


def test_jwt_payload_required_claims():
    payload = JwtPayload(sub="u-1", role="MLRO", status="ACTIVE", service="tx-auth")
    assert payload.sub == "u-1"
    assert payload.role == "MLRO"


def test_jwt_payload_rejects_missing_required():
    with pytest.raises(ValidationError):
        JwtPayload(sub="u-1", role="MLRO", status="ACTIVE")  # type: ignore[call-arg]


def test_jwt_payload_alias_coercion_email_verified():
    payload = JwtPayload.model_validate(
        {
            "sub": "u-1",
            "role": "MLRO",
            "status": "ACTIVE",
            "service": "tx-auth",
            "emailVerified": True,
            "phoneVerified": False,
        }
    )
    assert payload.email_verified is True
    assert payload.phone_verified is False


def test_jwt_payload_extra_claims_preserved():
    payload = JwtPayload.model_validate(
        {
            "sub": "u-1",
            "role": "MLRO",
            "status": "ACTIVE",
            "service": "tx-auth",
            "custom_org": "banxe-emi",
        }
    )
    dumped = payload.model_dump()
    assert dumped.get("custom_org") == "banxe-emi"


def test_jwt_payload_optional_iat_exp_jti():
    payload = JwtPayload(
        sub="u-1",
        role="MLRO",
        status="ACTIVE",
        service="tx-auth",
        iat=1700000000,
        exp=1700003600,
        jti="jti-1",
    )
    assert payload.iat == 1700000000
    assert payload.exp == 1700003600
    assert payload.jti == "jti-1"


# ── CompleteJwt ─────────────────────────────────────────────────────────────


def test_complete_jwt_constructs_from_typed_models():
    header = Jwks(kid="kid-x", alg="RS256")
    payload = JwtPayload(sub="u-1", role="CEO", status="ACTIVE", service="tx-auth")
    envelope = CompleteJwt(header=header, payload=payload)
    assert envelope.header.kid == "kid-x"
    assert envelope.payload.role == "CEO"


def test_complete_jwt_round_trip_via_dict():
    raw = {
        "header": {"kid": "kid-x", "alg": "RS256"},
        "payload": {
            "sub": "u-1",
            "role": "CEO",
            "status": "ACTIVE",
            "service": "tx-auth",
        },
    }
    envelope = CompleteJwt.model_validate(raw)
    dumped = envelope.model_dump()
    assert dumped["header"]["kid"] == "kid-x"
    assert dumped["payload"]["role"] == "CEO"
