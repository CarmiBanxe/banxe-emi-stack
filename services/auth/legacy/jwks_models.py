"""services/auth/legacy/jwks_models.py — pydantic models for JWKS / JWT payload.

Semantic 1-to-1 port of the BANXE.RAR TypeScript interfaces:
  - banxe-tx-auth/src/auth/interfaces/jwks.interface.ts (Jwks, Jwk, CompleteJwt)
  - banxe-tx-auth/src/auth/interfaces/jwtpayload.interface.ts (JwtPayload)

`JwksSet` is the RFC-7517 §5 JWKS document envelope (`{"keys": [Jwk, ...]}`).
The TS source did not declare it explicitly, but every JWKS HTTP endpoint
returns this shape, so we add it here for production parity.

Canon: ADR-015 (auth ports). No runtime behaviour, no network I/O.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Jwk(BaseModel):
    """RFC-7517 JSON Web Key — RSA per BANXE source schema.

    Fields mirror `banxe-tx-auth jwks.interface.ts::Jwk` exactly; additional
    optional RFC-7517 fields are accepted but ignored to remain forward-
    compatible with provider-specific extensions.
    """

    model_config = ConfigDict(extra="allow")

    kty: Literal["RSA"] = Field(description="Key type (RSA per source schema)")
    e: str = Field(description="RSA public exponent (base64url)")
    n: str = Field(description="RSA modulus (base64url)")
    use: str = Field(description="Public key use, e.g. 'sig'")
    kid: str = Field(description="Key ID (matches JWT header `kid`)")
    alg: str = Field(description="Algorithm name, e.g. 'RS256'")


class JwksSet(BaseModel):
    """RFC-7517 §5 JWKS envelope returned by `/.well-known/jwks.json`."""

    keys: list[Jwk] = Field(default_factory=list)

    def find(self, kid: str) -> Jwk | None:
        """Return the JWK with matching `kid`, or None if not present."""
        return next((k for k in self.keys if k.kid == kid), None)


class Jwks(BaseModel):
    """JWKS metadata wrapper used in token-issuer headers (BANXE source).

    Source `Jwks` carries only kid + alg + optional pem; production JWKS
    documents are represented by `JwksSet` above.
    """

    kid: str = Field(description="Key ID")
    alg: str = Field(description="Algorithm name")
    pem: str | None = Field(default=None, description="Optional PEM-encoded public key")


class JwtPayload(BaseModel):
    """JWT claims payload — port of `jwtpayload.interface.ts::JwtPayload`.

    Mirrors the BANXE source schema: `sub`, `role`, `status`, `service` are
    required; remaining RFC-7519 + BANXE extension fields are optional.
    """

    model_config = ConfigDict(extra="allow")

    sub: str = Field(description="Subject (user id)")
    role: str = Field(description="Gateway role (BanxeRole-compatible)")
    status: str = Field(description="Account status (ACTIVE / INACTIVE / ...)")
    service: str = Field(description="Originating service identifier")

    iat: int | None = Field(default=None, description="Issued-at unix time")
    exp: int | None = Field(default=None, description="Expiration unix time")
    jti: str | None = Field(default=None, description="JWT ID")
    email: str | None = Field(default=None)
    email_verified: bool | None = Field(default=None, alias="emailVerified")
    phone: str | None = Field(default=None)
    phone_verified: bool | None = Field(default=None, alias="phoneVerified")
    scope: str | None = Field(default=None)


class CompleteJwt(BaseModel):
    """Decoded JWT envelope — header + typed payload."""

    header: Jwks
    payload: JwtPayload
