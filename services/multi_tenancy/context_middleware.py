"""
services/multi_tenancy/context_middleware.py — Tenant context extraction + scope validation
IL-MT-01 | Phase 43 | banxe-emi-stack
"""

from __future__ import annotations

from contextvars import ContextVar
import uuid

from services.multi_tenancy.models import (
    InMemoryTenantPort,
    TenantContext,
    TenantPort,
    TenantStatus,
)

# Thread-safe context variable (PEP 567)
_current_tenant_ctx: ContextVar[TenantContext | None] = ContextVar(
    "_current_tenant_ctx", default=None
)


class TenantContextMiddleware:
    """Extracts, validates, and stores tenant context per request."""

    def __init__(self, tenant_port: TenantPort | None = None) -> None:
        self._tenants: TenantPort = tenant_port or InMemoryTenantPort()

    def extract_tenant_context(self, request_headers: dict[str, str]) -> TenantContext | None:
        """Extract TenantContext from request headers."""
        tenant_id = request_headers.get("X-Tenant-ID")
        user_id = request_headers.get("X-User-ID", "unknown")
        if not tenant_id:
            return None
        scopes_raw = request_headers.get("X-Scopes", "")
        scopes = [s.strip() for s in scopes_raw.split(",") if s.strip()]
        request_id = request_headers.get("X-Request-ID", str(uuid.uuid4()))
        return TenantContext(
            tenant_id=tenant_id,
            user_id=user_id,
            scopes=scopes,
            request_id=request_id,
        )

    def validate_tenant_active(self, tenant_id: str) -> bool:
        """Check that tenant exists and is ACTIVE."""
        tenant = self._tenants.get(tenant_id)
        return tenant is not None and tenant.status == TenantStatus.ACTIVE

    def get_current_tenant(self) -> TenantContext:
        """Get current tenant from context variable."""
        ctx = _current_tenant_ctx.get()
        if ctx is None:
            raise RuntimeError("No tenant context set for this request")
        return ctx

    def inject_tenant_context(
        self,
        tenant_id: str,
        user_id: str,
        scopes: list[str],
        request_id: str,
    ) -> TenantContext:
        """Inject tenant context into current context variable."""
        ctx = TenantContext(
            tenant_id=tenant_id,
            user_id=user_id,
            scopes=scopes,
            request_id=request_id,
        )
        _current_tenant_ctx.set(ctx)
        return ctx

    def require_tenant_scope(self, scope: str) -> bool:
        """Check if current tenant context has the required scope."""
        ctx = _current_tenant_ctx.get()
        if ctx is None:
            return False
        return scope in ctx.scopes

    def clear_context(self) -> None:
        """Clear tenant context (call at end of request)."""
        _current_tenant_ctx.set(None)
