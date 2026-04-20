"""
services/multi_tenancy/data_isolator.py — Data isolation enforcement
IL-MT-01 | Phase 43 | banxe-emi-stack
GDPR Art.25: privacy by design. Cross-tenant access always blocked by default.
"""

from __future__ import annotations

from services.multi_tenancy.models import (
    InMemoryTenantAuditPort,
    InMemoryTenantPort,
    IsolationLevel,
    TenantAuditEntry,
    TenantAuditPort,
    TenantPort,
)


class DataIsolator:
    """Enforces data isolation between tenants."""

    def __init__(
        self,
        tenant_port: TenantPort | None = None,
        audit_port: TenantAuditPort | None = None,
    ) -> None:
        self._tenants: TenantPort = tenant_port or InMemoryTenantPort()
        self._audit: TenantAuditPort = audit_port or InMemoryTenantAuditPort()
        # Explicit cross-tenant grants: {(source, target): bool}
        self._grants: dict[tuple[str, str], bool] = {}

    def get_tenant_schema(self, tenant_id: str) -> str:
        """Return DB schema name for SCHEMA isolation level."""
        tenant = self._tenants.get(tenant_id)
        if tenant is None:
            raise ValueError(f"Tenant {tenant_id!r} not found")
        if tenant.isolation_level == IsolationLevel.SCHEMA:
            return f"tenant_{tenant_id}"
        if tenant.isolation_level == IsolationLevel.DEDICATED:
            return f"tenant_{tenant_id}_dedicated"
        return "public"  # SHARED: all in public schema

    def get_connection_pool(self, tenant_id: str) -> str:
        """Return connection pool key for the tenant."""
        tenant = self._tenants.get(tenant_id)
        if tenant is None:
            raise ValueError(f"Tenant {tenant_id!r} not found")
        if tenant.isolation_level == IsolationLevel.DEDICATED:
            return f"pool_dedicated_{tenant_id}"
        if tenant.isolation_level == IsolationLevel.SCHEMA:
            return f"pool_schema_{tenant_id}"
        return "pool_shared"

    def validate_cross_tenant_access(self, source_tenant_id: str, target_tenant_id: str) -> bool:
        """Always False unless explicit grant was registered."""
        if source_tenant_id == target_tenant_id:
            return True
        return self._grants.get((source_tenant_id, target_tenant_id), False)

    def grant_cross_tenant_access(self, source_tenant_id: str, target_tenant_id: str) -> None:
        """Explicitly grant cross-tenant access (admin operation)."""
        self._grants[(source_tenant_id, target_tenant_id)] = True

    def create_row_filter(self, tenant_id: str) -> dict:
        """Create row-level filter for SHARED isolation."""
        return {"tenant_id": tenant_id}

    def audit_access(self, tenant_id: str, resource: str, actor: str) -> None:
        """Log data access for audit trail (I-14, I-24)."""
        from datetime import UTC, datetime
        import uuid

        entry = TenantAuditEntry(
            entry_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            action="DATA_ACCESS",
            actor=actor,
            timestamp=datetime.now(UTC).isoformat(),
            details={"resource": resource},
        )
        self._audit.append(entry)

    def get_isolation_level(self, tenant_id: str) -> IsolationLevel | None:
        """Get isolation level for tenant. Returns None if tenant not found."""
        tenant = self._tenants.get(tenant_id)
        if tenant is None:
            return None
        return tenant.isolation_level
