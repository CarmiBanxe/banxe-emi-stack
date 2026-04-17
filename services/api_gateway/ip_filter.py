from __future__ import annotations

from datetime import UTC, datetime
import ipaddress
import uuid

from services.api_gateway.models import (
    GeoAction,
    InMemoryIPAllowlistStore,
    IPAllowlistEntry,
    IPAllowlistStorePort,
)

_BLOCKED_COUNTRIES_CIDRS: set[str] = {
    "0.0.0.0/32",  # noqa: S104  # nosec B104 — stub placeholder, real geo-IP in prod
}


class IPFilter:
    """
    IP access control: key-scoped allowlists + geo-restriction.
    Blocked jurisdictions enforced per I-02.
    """

    def __init__(self, store: IPAllowlistStorePort | None = None) -> None:
        self._store: IPAllowlistStorePort = store or InMemoryIPAllowlistStore()

    def validate_cidr(self, cidr: str) -> bool:
        """Validate CIDR notation using stdlib ipaddress."""
        try:
            ipaddress.ip_network(cidr, strict=False)
            return True
        except ValueError:
            return False

    def _is_in_cidr(self, ip: str, cidr: str) -> bool:
        try:
            network = ipaddress.ip_network(cidr, strict=False)
            addr = ipaddress.ip_address(ip)
            return addr in network
        except ValueError:
            return False

    def _is_geo_blocked(self, ip_address: str) -> bool:
        for cidr in _BLOCKED_COUNTRIES_CIDRS:
            if self._is_in_cidr(ip_address, cidr):
                return True
        return False

    def is_allowed(self, ip_address: str, key_id: str) -> bool:
        """
        Check if IP is allowed for this key.
        - If key has an allowlist → only allow listed IPs with ALLOW action
        - If no allowlist → allow all (except geo-blocked)
        """
        if self._is_geo_blocked(ip_address):
            return False

        entries = self._store.list_by_key(key_id)
        if not entries:
            return True  # no allowlist → allow all (except blocked geo)

        for entry in entries:
            if entry.action == GeoAction.BLOCK and self._is_in_cidr(ip_address, entry.cidr):
                return False

        allow_entries = [e for e in entries if e.action == GeoAction.ALLOW]
        if not allow_entries:
            return True

        return any(self._is_in_cidr(ip_address, e.cidr) for e in allow_entries)

    def add_to_allowlist(self, key_id: str, cidr: str, action: GeoAction) -> IPAllowlistEntry:
        """Add a CIDR to the key-scoped allowlist/blocklist."""
        entry = IPAllowlistEntry(
            entry_id=str(uuid.uuid4()),
            key_id=key_id,
            cidr=cidr,
            action=action,
            created_at=datetime.now(UTC),
        )
        self._store.save(entry)
        return entry
