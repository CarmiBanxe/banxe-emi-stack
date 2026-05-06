"""services/auth/legacy/jwks_models.py — pydantic models for JWKS / JWK / CompleteJwt.

Type-only translation of the source TypeScript interfaces in
`banxe-tx-auth/src/auth/interfaces/jwks.interface.ts`. No runtime behaviour,
no network I/O — these models are consumed by `LegacyJwtStrategy` and any
future `TokenManagerPort.fetch_jwks()` adapter.

Canon: ADR-015 (auth ports). Scaffold only — not wired into production.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Jwk(BaseModel):
    """RFC-7517 JSON Web Key (RSA-only for the BANXE source schema)."""

    kty: Literal["RSA"] = Field(description="Key type (RSA per source schema)")
    e: str = Field(description="RSA exponent (base64url)")
    n: str = Field(description="RSA modulus (base64url)")
    use: str = Field(description="Public key use, e.g. 'sig'")
    kid: str = Field(description="Key ID")
    alg: str = Field(description="Algorithm name, e.g. 'RS256'")


class Jwks(BaseModel):
    """JWKS metadata wrapper used in token-issuer headers."""

    kid: str = Field(description="Key ID")
    alg: str = Field(description="Algorithm name")
    pem: str | None = Field(default=None, description="Optional PEM-encoded public key")


class CompleteJwt(BaseModel):
    """Decoded JWT envelope: header + payload."""

    header: Jwks
    payload: dict[str, Any] = Field(default_factory=dict)
