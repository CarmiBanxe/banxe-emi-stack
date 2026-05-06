"""services/auth/legacy/role_guard.py — scaffold for legacy role-check seam.

Future helper layer for `IAMPort.check_role(identity, roles)` semantics,
mirroring `banxe-tx-auth/src/auth/guard/role.guard.ts` invariant
`role ∈ allowed ∧ status == ACTIVE`.

Scaffold-only:
- not wired into FastAPI router
- not exported as a `Depends()` factory yet
- no import side-effects on `api/routers/auth.py`

Real implementation lands in a follow-up PR once the REWRITE classification
is approved. Until then, calling `LegacyRoleGuard.check()` raises
`NotImplementedError`.

Canon: ADR-015 (IAMPort), AUTH_IMPORT_ORDER.md (router transport-only).
"""

from __future__ import annotations

from collections.abc import Iterable


class LegacyRoleGuard:
    """Scaffold for legacy role check (BANXE.RAR `RoleGuard` → EMI IAMPort).

    `allowed_roles` is captured at construction; `check()` will be the
    boundary call once the adapter is implemented behind `IAMPort`.
    """

    def __init__(self, allowed_roles: Iterable[str]) -> None:
        self._allowed_roles: tuple[str, ...] = tuple(allowed_roles)

    @property
    def allowed_roles(self) -> tuple[str, ...]:
        """Return the configured allowed-role set (read-only)."""
        return self._allowed_roles

    def check(self, *, role: str, status: str) -> bool:
        """Return True if `role ∈ allowed_roles ∧ status == 'ACTIVE'`.

        Raises:
            NotImplementedError: scaffold seam; real adapter lands in a
                follow-up PR after REWRITE classification is approved.
        """
        raise NotImplementedError(
            "LegacyRoleGuard.check is a scaffold seam; "
            "adapter implementation pending Wave A REWRITE PR."
        )


def make_legacy_role_guard(*roles: str) -> LegacyRoleGuard:
    """Factory mirroring future FastAPI `Depends(require_roles(*roles))` shape.

    Returns a constructed `LegacyRoleGuard`. Does NOT register with FastAPI
    or any router — wiring is intentionally deferred to the adapter PR.
    """
    return LegacyRoleGuard(allowed_roles=roles)
