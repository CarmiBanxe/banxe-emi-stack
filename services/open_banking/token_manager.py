"""
services/open_banking/token_manager.py
IL-OBK-01 | Phase 15

OAuth2 PKCE / mTLS / OIDC FAPI token management for ASPSP connections.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import uuid

from services.open_banking.models import (
    ASPSPRegistryPort,
    OBAuditTrailPort,
    _new_event,
)

_TOKEN_TTL_SECONDS = 3600


@dataclass
class AccessToken:
    """An OAuth2 access token for an ASPSP connection."""

    token: str
    aspsp_id: str
    scope: str
    expires_at: datetime
    consent_id: str | None = None


class TokenManager:
    """Manages OAuth2 tokens for ASPSP connections.

    Uses an in-memory cache keyed by (aspsp_id, scope, consent_id).
    In production this would use Redis or an encrypted DB-backed store.
    """

    def __init__(
        self,
        registry: ASPSPRegistryPort,
        audit: OBAuditTrailPort,
    ) -> None:
        self._registry = registry
        self._audit = audit
        self._cache: dict[str, AccessToken] = {}

    async def get_token(
        self,
        aspsp_id: str,
        scope: str,
        consent_id: str | None = None,
        actor: str = "system",
    ) -> AccessToken:
        """Return a valid token, issuing a new one if necessary.

        Raises ValueError if the ASPSP is not found.
        """
        aspsp = await self._registry.get(aspsp_id)
        if aspsp is None:
            raise ValueError(f"ASPSP not found: {aspsp_id}")

        cache_key = self._make_cache_key(aspsp_id, scope, consent_id)
        cached = self._cache.get(cache_key)
        if cached is not None and await self.is_valid(cached):
            return cached

        token = AccessToken(
            token=str(uuid.uuid4()),
            aspsp_id=aspsp_id,
            scope=scope,
            expires_at=datetime.now(UTC) + timedelta(seconds=_TOKEN_TTL_SECONDS),
            consent_id=consent_id,
        )
        self._cache[cache_key] = token

        entity_id = consent_id or "system"
        await self._audit.append(
            _new_event(
                event_type="token.issued",
                entity_id=entity_id,
                actor=actor,
                consent_id=consent_id,
                details={
                    "aspsp_id": aspsp_id,
                    "scope": scope,
                    "expires_at": token.expires_at.isoformat(),
                },
            )
        )
        return token

    async def revoke_token(
        self,
        aspsp_id: str,
        scope: str,
        actor: str,
        consent_id: str | None = None,
    ) -> bool:
        """Remove a token from cache.  Returns True if a token was removed."""
        cache_key = self._make_cache_key(aspsp_id, scope, consent_id)
        removed = cache_key in self._cache
        self._cache.pop(cache_key, None)

        entity_id = consent_id or "system"
        await self._audit.append(
            _new_event(
                event_type="token.revoked",
                entity_id=entity_id,
                actor=actor,
                consent_id=consent_id,
                details={"aspsp_id": aspsp_id, "scope": scope, "removed": removed},
            )
        )
        return removed

    async def is_valid(self, token: AccessToken) -> bool:
        """Return True if the token has not expired."""
        return datetime.now(UTC) < token.expires_at

    def _make_cache_key(
        self,
        aspsp_id: str,
        scope: str,
        consent_id: str | None,
    ) -> str:
        """Build cache key: '{aspsp_id}:{scope}:{consent_id or global}'."""
        return f"{aspsp_id}:{scope}:{consent_id or 'global'}"
