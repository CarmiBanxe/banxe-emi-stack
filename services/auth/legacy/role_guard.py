"""services/auth/legacy/role_guard.py — production role-check adapter.

Port-compliant role-guard adapter aligned with `IAMPort.authorize` semantics.
Semantic 1-to-1 transposition of:
  banxe-tx-auth/src/auth/guard/role.guard.ts

Source invariant (TS):
    return _roles.includes(user.role) && user.status === StatusEnum.ACTIVE

Adapter exposes:
  - `LegacyRoleGuardAdapter.check(role, status) -> bool` — pure invariant.
  - `require_roles(*roles, jwt_strategy)` — FastAPI dependency factory that
    extracts Bearer token, validates via `LegacyJwtStrategyAdapter`, then
    enforces the role+status invariant. Returns the verified claims dict on
    success, raises `HTTPException(401|403)` on failure.

Canon: ADR-015 (IAMPort), AUTH_IMPORT_ORDER (router transport-only).
This module deliberately avoids importing or referencing FastAPI router
modules — it provides only a `Depends()`-shaped factory.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from fastapi import Header, HTTPException, status

from services.auth.legacy.jwt_strategy import LegacyJwtStrategyAdapter, TokenValidationError

ACTIVE_STATUS = "ACTIVE"
"""Source `StatusEnum.ACTIVE` — only this status passes the role guard."""


class LegacyRoleGuardAdapter:
    """Pure role-check invariant: `role in allowed_roles AND status == 'ACTIVE'`.

    Mirrors `RoleGuard.canActivate` semantics from the BANXE source, minus the
    JWT decode step (which is moved upstream into `LegacyJwtStrategyAdapter`).
    """

    def __init__(self, allowed_roles: Iterable[str]) -> None:
        self._allowed_roles: tuple[str, ...] = tuple(allowed_roles)

    @property
    def allowed_roles(self) -> tuple[str, ...]:
        """Return the configured allowed-role set (read-only)."""
        return self._allowed_roles

    def check(self, *, role: str, status: str) -> bool:
        """Return True if `role ∈ allowed_roles AND status == 'ACTIVE'`."""
        return role in self._allowed_roles and status == ACTIVE_STATUS


def require_roles(
    *roles: str,
    jwt_strategy: LegacyJwtStrategyAdapter,
) -> Callable[..., dict[str, Any]]:
    """Build a FastAPI dependency enforcing the role/status invariant.

    Usage in a router (router file untouched in this PR — example only)::

        guard = require_roles("MLRO", "CEO", jwt_strategy=adapter)
        @router.get("/mlro/queue")
        def queue(claims: dict = Depends(guard)) -> ...:
            ...

    Returns:
        A callable suitable as a FastAPI `Depends()` dependency. On success it
        returns the verified claims dict (`{userId, role, status, service}`).

    Raises (inside the dependency):
        HTTPException(401): missing / malformed Bearer header, JWT invalid,
            JWKS lookup miss, or token expired.
        HTTPException(403): claims valid but role/status invariant failed.
    """
    if not roles:
        raise ValueError("require_roles requires at least one role")

    guard = LegacyRoleGuardAdapter(allowed_roles=roles)

    def _dependency(authorization: str = Header(..., alias="Authorization")) -> dict[str, Any]:
        if not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing Bearer token",
            )
        token = authorization[len("Bearer ") :].strip()
        try:
            claims = jwt_strategy.validate_access_token(token)
        except TokenValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=exc.message,
            ) from exc

        if not guard.check(role=str(claims.get("role", "")), status=str(claims.get("status", ""))):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Role or status check failed",
            )
        return claims

    return _dependency


def make_legacy_role_guard(*roles: str) -> LegacyRoleGuardAdapter:
    """Factory returning a `LegacyRoleGuardAdapter` for the given roles.

    Provided for back-compat with PR #74 scaffold tests; production code
    should use `require_roles(...)` to obtain a FastAPI dependency.
    """
    return LegacyRoleGuardAdapter(allowed_roles=roles)


# Backward-compat alias for the scaffold name used in PR #74 tests.
LegacyRoleGuard = LegacyRoleGuardAdapter
