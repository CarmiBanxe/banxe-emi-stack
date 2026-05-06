"""services/auth/legacy/jwt_strategy.py — scaffold for legacy JWT validation seam.

Future adapter seam for legacy/BANXE-RAR JWT validation behind the
TokenManager / IAM boundary. Mirrors the source `banxe-tx-auth/src/auth/strategy/
jwt.strategy.ts` claims schema (`{userId, role, status, service}`) and is intended
to be wired behind `TokenManagerPort.validate(token)` once the REWRITE step lands.

This module is *scaffold-only*: no production wiring, no real BANXE.RAR code
imports, no network I/O. The `validate()` method raises `NotImplementedError`
until the adapter is implemented in a follow-up PR.

Canon: ADR-015 (auth ports), AUTH_IMPORT_ORDER.md (router transport-only).
"""

from __future__ import annotations

from typing import Any

ClaimsDict = dict[str, Any]
"""Type alias for JWT claims payload returned by validate()."""


class LegacyJwtStrategy:
    """Scaffold for legacy JWT validation seam (BANXE.RAR → EMI port).

    Designed to be plugged behind `TokenManagerPort.validate(token)`. Real
    implementation will use `pyjwt` + `jwcrypto` for RFC-7519 / RFC-7517
    parity with the source NestJS Passport JwtStrategy.

    Constructor takes future config (issuer, audience, JWKS source) but does
    nothing yet — kept for stable signature when the adapter is implemented.
    """

    def __init__(
        self,
        *,
        issuer: str | None = None,
        audience: str | None = None,
        jwks_source: str | None = None,
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._jwks_source = jwks_source

    def validate(self, token: str) -> ClaimsDict:
        """Validate a JWT and return its claims payload.

        Returns a `ClaimsDict` (dict[str, Any]) compatible with the legacy
        BANXE source schema `{userId, role, status, service}`.

        Raises:
            NotImplementedError: scaffold seam; real adapter lands in a
                follow-up PR after REWRITE classification is approved.
        """
        raise NotImplementedError(
            "LegacyJwtStrategy.validate is a scaffold seam; "
            "adapter implementation pending Wave A REWRITE PR."
        )
