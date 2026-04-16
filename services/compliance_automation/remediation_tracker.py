"""
services/compliance_automation/remediation_tracker.py
IL-CAE-01 | Phase 23

Remediation workflow tracker — state machine for compliance finding resolution.
Valid transitions: OPEN → ASSIGNED → IN_PROGRESS → RESOLVED → VERIFIED → CLOSED.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from uuid import uuid4

from services.compliance_automation.models import (
    Remediation,
    RemediationStatus,
    RemediationStorePort,
)

# State machine: valid next states keyed by current state
_VALID_TRANSITIONS: dict[RemediationStatus, set[RemediationStatus]] = {
    RemediationStatus.OPEN: {RemediationStatus.ASSIGNED},
    RemediationStatus.ASSIGNED: {RemediationStatus.IN_PROGRESS},
    RemediationStatus.IN_PROGRESS: {RemediationStatus.RESOLVED},
    RemediationStatus.RESOLVED: {RemediationStatus.VERIFIED},
    RemediationStatus.VERIFIED: {RemediationStatus.CLOSED},
    RemediationStatus.CLOSED: set(),
}

_OPEN_STATUSES: set[RemediationStatus] = {
    RemediationStatus.OPEN,
    RemediationStatus.ASSIGNED,
    RemediationStatus.IN_PROGRESS,
    RemediationStatus.RESOLVED,
}


class RemediationTracker:
    """Tracks compliance remediation items through a defined state machine."""

    def __init__(self, remediation_store: RemediationStorePort) -> None:
        self._store = remediation_store

    async def create_remediation(
        self,
        check_id: str,
        entity_id: str,
        finding: str,
        assigned_to: str,
        due_date: datetime,
    ) -> Remediation:
        """Create a new remediation item in OPEN status."""
        remediation = Remediation(
            remediation_id=str(uuid4()),
            check_id=check_id,
            entity_id=entity_id,
            finding=finding,
            status=RemediationStatus.OPEN,
            assigned_to=assigned_to,
            due_date=due_date,
            resolved_at=None,
            created_at=datetime.now(UTC),
        )
        return await self._store.save_remediation(remediation)

    async def update_status(
        self,
        remediation_id: str,
        new_status: RemediationStatus,
    ) -> Remediation:
        """Advance remediation to new_status; raises ValueError for invalid transitions."""
        remediation = await self._store.get_remediation(remediation_id)
        if remediation is None:
            raise ValueError(f"Remediation not found: {remediation_id}")

        allowed = _VALID_TRANSITIONS.get(remediation.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Invalid transition: {remediation.status} → {new_status}. Allowed: {allowed}"
            )

        resolved_at = remediation.resolved_at
        if new_status == RemediationStatus.RESOLVED:
            resolved_at = datetime.now(UTC)

        updated = dataclasses.replace(
            remediation,
            status=new_status,
            resolved_at=resolved_at,
        )
        return await self._store.save_remediation(updated)

    async def get_remediation(self, remediation_id: str) -> Remediation | None:
        """Fetch a single remediation by ID."""
        return await self._store.get_remediation(remediation_id)

    async def list_open_remediations(
        self,
        entity_id: str | None = None,
    ) -> list[Remediation]:
        """Return remediations not yet CLOSED or VERIFIED."""
        all_items = await self._store.list_remediations(entity_id=entity_id)
        return [r for r in all_items if r.status in _OPEN_STATUSES]
