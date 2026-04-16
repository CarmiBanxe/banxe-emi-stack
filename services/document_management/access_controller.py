"""
services/document_management/access_controller.py — AccessController
IL-DMS-01 | Phase 24 | banxe-emi-stack

Role-based access control for documents. Enforces AccessLevel hierarchy per role.
Deletion requires Compliance Officer or Admin role (HITL L4, I-27).
"""

from __future__ import annotations

from datetime import UTC, datetime
import uuid

from services.document_management.models import (
    AccessLevel,
    AccessLogPort,
    AccessRecord,
    DocumentStorePort,
)

# Role → set of accessible access levels
_ROLE_ACCESS: dict[str, set[AccessLevel]] = {
    "admin": {
        AccessLevel.PUBLIC,
        AccessLevel.INTERNAL,
        AccessLevel.CONFIDENTIAL,
        AccessLevel.RESTRICTED,
    },
    "compliance_officer": {
        AccessLevel.PUBLIC,
        AccessLevel.INTERNAL,
        AccessLevel.CONFIDENTIAL,
        AccessLevel.RESTRICTED,
    },
    "mlro": {
        AccessLevel.PUBLIC,
        AccessLevel.INTERNAL,
        AccessLevel.CONFIDENTIAL,
        AccessLevel.RESTRICTED,
    },
    "analyst": {
        AccessLevel.PUBLIC,
        AccessLevel.INTERNAL,
        AccessLevel.CONFIDENTIAL,
    },
    "support": {
        AccessLevel.PUBLIC,
        AccessLevel.INTERNAL,
    },
    "customer": {
        AccessLevel.PUBLIC,
    },
}

# Only these roles may delete documents (HITL L4 applies, I-27)
_DELETE_ROLES: frozenset[str] = frozenset({"admin", "compliance_officer"})


class AccessController:
    """Enforces role-based access to documents and logs all access attempts."""

    def __init__(
        self,
        access_log: AccessLogPort,
        document_store: DocumentStorePort,
    ) -> None:
        self._access_log = access_log
        self._docs = document_store

    async def check_access(
        self,
        doc_id: str,
        role: str,
        action: str,
    ) -> bool:
        """
        Check if a role may access a document and log the attempt.

        Logs action="ACCESS_DENIED" if access is denied.
        Returns True if allowed, False if denied.
        """
        doc = await self._docs.get(doc_id)
        if doc is None:
            record = AccessRecord(
                record_id=str(uuid.uuid4()),
                doc_id=doc_id,
                accessed_by=role,
                action="ACCESS_DENIED",
                ip_address="0.0.0.0",  # noqa: S104  # nosec B104
                accessed_at=datetime.now(UTC),
            )
            await self._access_log.log_access(record)
            return False

        allowed_levels = _ROLE_ACCESS.get(role, set())
        allowed = doc.access_level in allowed_levels

        log_action = action if allowed else "ACCESS_DENIED"
        record = AccessRecord(
            record_id=str(uuid.uuid4()),
            doc_id=doc_id,
            accessed_by=role,
            action=log_action,
            ip_address="0.0.0.0",  # noqa: S104  # nosec B104
            accessed_at=datetime.now(UTC),
        )
        await self._access_log.log_access(record)

        return allowed

    async def get_access_log(self, doc_id: str) -> list[AccessRecord]:
        """Return the append-only access log for a document (I-24)."""
        return await self._access_log.list_access(doc_id)

    async def can_delete(self, role: str) -> bool:
        """Return True only for roles permitted to delete documents (HITL L4)."""
        return role in _DELETE_ROLES
