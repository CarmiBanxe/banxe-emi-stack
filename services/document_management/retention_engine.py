"""
services/document_management/retention_engine.py — RetentionEngine
IL-DMS-01 | Phase 24 | banxe-emi-stack

Regulatory retention period enforcement:
- MLR 2017 Reg.40: KYC/AML records 5 years
- SYSC 9: POLICY/REGULATORY permanent; REPORT 7 years
"""

from __future__ import annotations

from datetime import UTC, datetime

from services.document_management.models import (
    AccessLogPort,
    Document,
    DocumentCategory,
    DocumentStorePort,
    RetentionPeriod,
    RetentionPolicy,
    RetentionStorePort,
)

# Days per retention period; None = PERMANENT (no expiry)
_RETENTION_DAYS: dict[RetentionPeriod, int | None] = {
    RetentionPeriod.YEARS_5: 1825,
    RetentionPeriod.YEARS_7: 2555,
    RetentionPeriod.YEARS_10: 3650,
    RetentionPeriod.PERMANENT: None,
}


class RetentionEngine:
    """Evaluates document retention compliance against regulatory policies."""

    def __init__(
        self,
        retention_store: RetentionStorePort,
        document_store: DocumentStorePort,
        access_log: AccessLogPort,
    ) -> None:
        self._retention = retention_store
        self._docs = document_store
        self._access_log = access_log

    async def get_retention_policy(self, category: DocumentCategory) -> RetentionPolicy | None:
        """Return the retention policy for a given document category."""
        return await self._retention.get_policy(category)

    async def check_retention(self, doc: Document) -> dict:
        """
        Evaluate whether a document has exceeded its retention period.

        Returns:
            dict with doc_id, category, retention_days, days_stored, action_required.
            action_required=True when retention_days is set and days_stored > retention_days.
        """
        policy = await self._retention.get_policy(doc.category)
        retention_days: int | None = None

        if policy is not None:
            retention_days = _RETENTION_DAYS.get(policy.retention_period)

        now = datetime.now(UTC)
        days_stored = (now - doc.created_at).days

        action_required = retention_days is not None and days_stored > retention_days

        return {
            "doc_id": doc.doc_id,
            "category": doc.category.value,
            "retention_days": retention_days,
            "days_stored": days_stored,
            "action_required": action_required,
        }

    async def list_policies(self) -> list[RetentionPolicy]:
        """Return all configured retention policies."""
        return await self._retention.list_policies()

    async def apply_retention_check(self, entity_id: str) -> list[dict]:
        """
        Check all documents for an entity and return those requiring action.

        Returns list of retention check results where action_required=True.
        """
        docs = await self._docs.list_by_entity(entity_id=entity_id, category=None)
        results = []
        for doc in docs:
            check = await self.check_retention(doc)
            if check["action_required"]:
                results.append(check)
        return results
