"""
services/document_management/version_manager.py — VersionManager
IL-DMS-01 | Phase 24 | banxe-emi-stack

Document versioning: create, retrieve, and rollback document versions.
SHA-256 hashing for version integrity.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import uuid

from services.document_management.models import (
    AccessLogPort,
    AccessRecord,
    DocumentStorePort,
    DocumentVersion,
    VersionStorePort,
)


class VersionManager:
    """Manages document version history with rollback support."""

    def __init__(
        self,
        document_store: DocumentStorePort,
        version_store: VersionStorePort,
        access_log: AccessLogPort,
    ) -> None:
        self._docs = document_store
        self._versions = version_store
        self._access_log = access_log

    async def create_version(
        self,
        doc_id: str,
        new_content: str,
        change_note: str,
        created_by: str,
    ) -> DocumentVersion:
        """Create a new version for a document."""
        existing = await self._versions.list_versions(doc_id)
        next_number = max((v.version_number for v in existing), default=0) + 1
        content_hash = hashlib.sha256(new_content.encode()).hexdigest()
        now = datetime.now(UTC)

        version = DocumentVersion(
            version_id=str(uuid.uuid4()),
            doc_id=doc_id,
            version_number=next_number,
            content_hash=content_hash,
            change_note=change_note,
            created_by=created_by,
            created_at=now,
        )
        await self._versions.save_version(version)

        access_record = AccessRecord(
            record_id=str(uuid.uuid4()),
            doc_id=doc_id,
            accessed_by=created_by,
            action="UPDATE",
            ip_address="0.0.0.0",  # noqa: S104  # nosec B104
            accessed_at=now,
        )
        await self._access_log.log_access(access_record)

        return version

    async def get_versions(self, doc_id: str) -> list[DocumentVersion]:
        """Return all versions sorted by version_number ascending."""
        versions = await self._versions.list_versions(doc_id)
        return sorted(versions, key=lambda v: v.version_number)

    async def get_latest_version(self, doc_id: str) -> DocumentVersion | None:
        """Return the latest (highest version_number) version."""
        versions = await self.get_versions(doc_id)
        if not versions:
            return None
        return versions[-1]

    async def rollback(
        self,
        doc_id: str,
        version_number: int,
        actor: str,
    ) -> DocumentVersion:
        """Rollback by creating a new version with the old content hash."""
        versions = await self._versions.list_versions(doc_id)
        target = next((v for v in versions if v.version_number == version_number), None)
        if target is None:
            raise ValueError(f"Version {version_number} not found for document {doc_id}")

        existing_numbers = [v.version_number for v in versions]
        next_number = max(existing_numbers) + 1
        now = datetime.now(UTC)

        rollback_version = DocumentVersion(
            version_id=str(uuid.uuid4()),
            doc_id=doc_id,
            version_number=next_number,
            content_hash=target.content_hash,
            change_note=f"Rollback to v{version_number}",
            created_by=actor,
            created_at=now,
        )
        await self._versions.save_version(rollback_version)

        access_record = AccessRecord(
            record_id=str(uuid.uuid4()),
            doc_id=doc_id,
            accessed_by=actor,
            action="UPDATE",
            ip_address="0.0.0.0",  # noqa: S104  # nosec B104
            accessed_at=now,
        )
        await self._access_log.log_access(access_record)

        return rollback_version
