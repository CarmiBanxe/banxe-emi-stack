"""
services/multi_tenancy/isolation_validator.py — Isolation & GDPR compliance validation
IL-MT-01 | Phase 43 | banxe-emi-stack
CASS 7: client money pool separation per tenant.
GDPR Art.25: privacy by design — data residence validation.
"""

from __future__ import annotations

from services.multi_tenancy.models import (
    InMemoryTenantPort,
    IsolationLevel,
    TenantPort,
    TenantStatus,
)

# EU/EEA countries for GDPR Art.25 data residence
GDPR_PERMITTED_REGIONS: frozenset[str] = frozenset(
    {
        "GB",
        "EU",
        "DE",
        "FR",
        "NL",
        "IE",
        "LU",
        "SE",
        "FI",
        "DK",
        "NO",
        "IS",
        "LI",  # EEA additions
    }
)


class IsolationValidator:
    """Validates data isolation and regulatory compliance."""

    def __init__(self, tenant_port: TenantPort | None = None) -> None:
        self._tenants: TenantPort = tenant_port or InMemoryTenantPort()

    def validate_request_isolation(self, tenant_id: str, resource_tenant_id: str) -> bool:
        """Check request is accessing resources belonging to the same tenant."""
        return tenant_id == resource_tenant_id

    def check_data_leakage(self, response_data: dict, expected_tenant_id: str) -> list[str]:
        """Detect tenant ID leakage in response data."""
        warnings: list[str] = []
        tenant_id_in_data = response_data.get("tenant_id")
        if tenant_id_in_data and tenant_id_in_data != expected_tenant_id:
            warnings.append(
                f"tenant_id mismatch: got {tenant_id_in_data!r}, expected {expected_tenant_id!r}"
            )
        items = response_data.get("items", [])
        for i, item in enumerate(items):
            if isinstance(item, dict):
                item_tid = item.get("tenant_id")
                if item_tid and item_tid != expected_tenant_id:
                    warnings.append(f"items[{i}].tenant_id mismatch: {item_tid!r}")
        return warnings

    def validate_cass_pool_separation(self, tenant_id: str) -> bool:
        """CASS 7: verify tenant has separate client money pool."""
        tenant = self._tenants.get(tenant_id)
        if tenant is None:
            return False
        if tenant.status != TenantStatus.ACTIVE:
            return False
        return tenant.cass_pool_id is not None and tenant.cass_pool_id != ""

    def generate_isolation_report(self, tenant_id: str) -> dict:
        """Generate isolation compliance report for tenant."""
        tenant = self._tenants.get(tenant_id)
        if tenant is None:
            return {"tenant_id": tenant_id, "error": "not found"}
        cass_ok = self.validate_cass_pool_separation(tenant_id)
        return {
            "tenant_id": tenant_id,
            "isolation_level": tenant.isolation_level.value,
            "cass_pool_id": tenant.cass_pool_id,
            "cass_compliant": cass_ok,
            "status": tenant.status.value,
            "tier": tenant.tier.value,
            "gdpr_jurisdiction": tenant.jurisdiction,
        }

    def assert_gdpr_data_residence(self, tenant_id: str, data_region: str) -> bool:
        """GDPR Art.25: verify data is stored in permitted region."""
        tenant = self._tenants.get(tenant_id)
        if tenant is None:
            return False
        if data_region not in GDPR_PERMITTED_REGIONS:
            return False
        # Tenant jurisdiction must also be non-blocked
        if tenant.jurisdiction in {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}:
            return False
        return True

    def get_isolation_level(self, tenant_id: str) -> IsolationLevel | None:
        """Get isolation level for tenant."""
        tenant = self._tenants.get(tenant_id)
        if tenant is None:
            return None
        return tenant.isolation_level
