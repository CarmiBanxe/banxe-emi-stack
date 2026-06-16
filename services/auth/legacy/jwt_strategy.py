"""services/auth/legacy/jwt_strategy.py — production JWT validation adapter.

Port-compliant adapter for legacy BANXE.RAR JWT validation behind the
`TokenManagerPort` Protocol. Semantic 1-to-1 transposition of:
  banxe-tx-auth/src/auth/strategy/jwt.strategy.ts

Source uses `passport-jwt` with `jwks-rsa` for JWKS-backed RS256 verification
and returns `{userId, role, status, service}`. This adapter reproduces those
semantics in Python with `pyjwt` + a pluggable `jwks_provider` so tests can
inject keys without HTTP I/O.

Issue / refresh remain owned by `services/auth/token_manager.py` core; this
adapter is read-only validation only.

Canon: ADR-015 (TokenManagerPort), AUTH_IMPORT_ORDER (router transport-only).
"""

from __future__ import annotations

from collections.abc import Callable
import json
import logging
from typing import Any
from urllib.request import Request, urlopen

import jwt
from jwt.algorithms import RSAAlgorithm

from services.auth.legacy.jwks_models import Jwk, JwksSet

logger = logging.getLogger("banxe.auth.legacy.jwt_strategy")

ClaimsDict = dict[str, Any]
"""Type alias for the claims payload returned by `validate_access_token`."""

DEFAULT_ALGORITHMS: tuple[str, ...] = ("RS256",)
DEFAULT_JWKS_TIMEOUT_SEC = 5

JwksProvider = Callable[[], JwksSet]
"""Pluggable JWKS source — returns the current key set."""


class TokenValidationError(Exception):
    """Raised on any JWT validation failure (signature, expiry, claims)."""

    def __init__(self, message: str, code: str = "invalid_token") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class LegacyJwtStrategyAdapter:
    """Validate-only JWT adapter implementing `TokenManagerPort.validate_access_token`.

    Constructor accepts EITHER a `jwks_uri` (production: HTTP-fetched JWKS) OR a
    `jwks_provider` callable (tests / DI). At least one must be supplied.

    Source parity (`banxe-tx-auth jwt.strategy.ts::validate`):
        return {userId: payload.sub, role: payload.role,
                status: payload.status, service: payload.service}
    """

    def __init__(
        self,
        *,
        jwks_uri: str | None = None,
        jwks_provider: JwksProvider | None = None,
        algorithms: tuple[str, ...] = DEFAULT_ALGORITHMS,
        audience: str | None = None,
        issuer: str | None = None,
        jwks_timeout_sec: int = DEFAULT_JWKS_TIMEOUT_SEC,
    ) -> None:
        if jwks_uri is None and jwks_provider is None:
            raise ValueError("LegacyJwtStrategyAdapter requires either jwks_uri or jwks_provider")
        self._jwks_uri = jwks_uri
        self._jwks_provider = jwks_provider
        self._algorithms = algorithms
        self._audience = audience
        self._issuer = issuer
        self._jwks_timeout_sec = jwks_timeout_sec
        self._jwks_cache: JwksSet | None = None

    # ── public ────────────────────────────────────────────────────────────────

    def validate_access_token(self, token: str) -> ClaimsDict:
        """Verify JWT signature + standard claims, return BANXE claim schema.

        Returns a `ClaimsDict` mirroring source TS:
            {"userId": <sub>, "role": <role>, "status": <status>, "service": <service>}

        Raises:
            TokenValidationError: on invalid signature, expiry, missing kid,
                JWKS lookup miss, or missing required claims.
        """
        if not isinstance(token, str) or not token:
            raise TokenValidationError("Empty or non-string token", code="invalid_token")

        try:
            unverified_header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise TokenValidationError(
                f"Malformed JWT header: {exc}", code="invalid_token"
            ) from exc

        kid = unverified_header.get("kid")
        if not kid:
            raise TokenValidationError("JWT header missing 'kid'", code="invalid_token")

        jwk = self._lookup_key(kid)
        if jwk is None:
            raise TokenValidationError(f"No JWK found for kid={kid!r}", code="kid_mismatch")

        public_key = RSAAlgorithm.from_jwk(jwk.model_dump_json())

        decode_kwargs: dict[str, Any] = {
            "algorithms": list(self._algorithms),
        }
        if self._audience is not None:
            decode_kwargs["audience"] = self._audience
        if self._issuer is not None:
            decode_kwargs["issuer"] = self._issuer

        try:
            payload = jwt.decode(token, key=public_key, **decode_kwargs)
        except jwt.ExpiredSignatureError as exc:
            raise TokenValidationError("Token expired", code="token_expired") from exc
        except jwt.InvalidTokenError as exc:
            raise TokenValidationError(
                f"Token validation failed: {exc}", code="invalid_token"
            ) from exc

        return self._project_claims(payload)

    # ── internals ─────────────────────────────────────────────────────────────

    def _lookup_key(self, kid: str) -> Jwk | None:
        jwks = self._load_jwks()
        return jwks.find(kid)

    def _load_jwks(self) -> JwksSet:
        if self._jwks_cache is not None:
            return self._jwks_cache

        if self._jwks_provider is not None:
            jwks = self._jwks_provider()
        else:
            jwks = self._fetch_jwks_http()

        self._jwks_cache = jwks
        return jwks

    def _fetch_jwks_http(self) -> JwksSet:
        if self._jwks_uri is None:
            raise TokenValidationError("jwks_uri not configured", code="jwks_fetch_failed")
        if not self._jwks_uri.startswith(("https://", "http://")):
            raise TokenValidationError(
                f"Refusing JWKS fetch from non-http(s) URI: {self._jwks_uri!r}",
                code="jwks_fetch_failed",
            )
        try:
            req = Request(self._jwks_uri, headers={"Accept": "application/json"})  # noqa: S310  # nosec B310 — scheme guarded above
            with urlopen(req, timeout=self._jwks_timeout_sec) as resp:  # noqa: S310  # nosec B310 — scheme guarded above  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected  # https scheme guarded JWKS fetch (nosec B310)
                raw = resp.read().decode("utf-8")
        except Exception as exc:  # network / parse / SSL — uniform error
            raise TokenValidationError(
                f"JWKS fetch failed: {exc}", code="jwks_fetch_failed"
            ) from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TokenValidationError(
                f"JWKS body is not valid JSON: {exc}", code="jwks_fetch_failed"
            ) from exc

        return JwksSet.model_validate(data)

    @staticmethod
    def _project_claims(payload: dict[str, Any]) -> ClaimsDict:
        """Project verified payload onto the BANXE source claim schema."""
        for required in ("sub", "role", "status", "service"):
            if required not in payload:
                raise TokenValidationError(
                    f"Missing required claim: {required!r}", code="missing_claim"
                )
        return {
            "userId": payload["sub"],
            "role": payload["role"],
            "status": payload["status"],
            "service": payload["service"],
        }


# Backward-compat alias for the scaffold name used in PR #74 tests.
LegacyJwtStrategy = LegacyJwtStrategyAdapter
