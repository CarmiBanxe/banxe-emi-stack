"""
services/compliance_automation/policy_manager.py
IL-CAE-01 | Phase 23

Policy lifecycle management — DRAFT → REVIEW → ACTIVE → RETIRED.
Immutable version history; dataclasses.replace() for state transitions.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from uuid import uuid4

from services.compliance_automation.models import (
    PolicyStatus,
    PolicyStorePort,
    PolicyVersion,
)


class PolicyManager:
    """Manages the lifecycle and versioning of compliance policies."""

    def __init__(self, policy_store: PolicyStorePort) -> None:
        self._policy_store = policy_store

    async def create_policy(
        self,
        policy_id: str,
        content: str,
        author: str,
    ) -> PolicyVersion:
        """Create a new policy as version 1 in DRAFT status."""
        version = PolicyVersion(
            version_id=str(uuid4()),
            policy_id=policy_id,
            version_number=1,
            content=content,
            status=PolicyStatus.DRAFT,
            author=author,
            created_at=datetime.now(UTC),
            approved_at=None,
        )
        return await self._policy_store.save_version(version)

    async def submit_for_review(self, version_id: str) -> PolicyVersion:
        """Transition DRAFT → REVIEW."""
        version = await self._policy_store.get_version(version_id)
        if version is None:
            raise ValueError(f"PolicyVersion not found: {version_id}")
        updated = dataclasses.replace(version, status=PolicyStatus.REVIEW)
        return await self._policy_store.save_version(updated)

    async def approve_policy(self, version_id: str, approved_by: str) -> PolicyVersion:
        """Transition REVIEW → ACTIVE and record approval timestamp."""
        version = await self._policy_store.get_version(version_id)
        if version is None:
            raise ValueError(f"PolicyVersion not found: {version_id}")
        updated = dataclasses.replace(
            version,
            status=PolicyStatus.ACTIVE,
            approved_at=datetime.now(UTC),
        )
        return await self._policy_store.save_version(updated)

    async def retire_policy(self, version_id: str) -> PolicyVersion:
        """Transition ACTIVE → RETIRED."""
        version = await self._policy_store.get_version(version_id)
        if version is None:
            raise ValueError(f"PolicyVersion not found: {version_id}")
        updated = dataclasses.replace(version, status=PolicyStatus.RETIRED)
        return await self._policy_store.save_version(updated)

    async def get_policy_history(self, policy_id: str) -> list[PolicyVersion]:
        """Return all versions of a policy sorted by version_number ascending."""
        versions = await self._policy_store.list_versions(policy_id)
        return sorted(versions, key=lambda v: v.version_number)

    async def diff_versions(self, policy_id: str, v1: int, v2: int) -> dict:
        """Compare content of two version numbers for a given policy."""
        versions = await self._policy_store.list_versions(policy_id)
        by_number = {v.version_number: v for v in versions}

        version1 = by_number.get(v1)
        if version1 is None:
            raise ValueError(f"Version {v1} not found for policy {policy_id}")

        version2 = by_number.get(v2)
        if version2 is None:
            raise ValueError(f"Version {v2} not found for policy {policy_id}")

        return {
            "policy_id": policy_id,
            "v1": v1,
            "v2": v2,
            "v1_content": version1.content,
            "v2_content": version2.content,
            "changed": version1.content != version2.content,
        }
