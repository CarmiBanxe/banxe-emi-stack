"""
services/audit_trail/retention_enforcer.py
IL-AES-01 | Phase 40 | banxe-emi-stack

RetentionEnforcer — audit record retention policy management.
I-27: Purge is ALWAYS HITL — deleting audit records is irreversible.
I-08: Minimum 5-year retention (FCA requirement).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from services.audit_trail.models import (
    AuditEvent,
    EventCategory,
    EventStorePort,
    InMemoryEventStorePort,
    RetentionPolicy,
    RetentionRule,
)


@dataclass
class HITLProposal:
    action: str
    resource_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


DEFAULT_RULES: dict[RetentionPolicy, RetentionRule] = {
    RetentionPolicy.AML_5YR: RetentionRule(RetentionPolicy.AML_5YR, 1825, EventCategory.AML, True),
    RetentionPolicy.FINANCIAL_7YR: RetentionRule(
        RetentionPolicy.FINANCIAL_7YR, 2555, EventCategory.PAYMENT, True
    ),
    RetentionPolicy.OPERATIONAL_3YR: RetentionRule(
        RetentionPolicy.OPERATIONAL_3YR, 1095, EventCategory.SYSTEM, True
    ),
    RetentionPolicy.SYSTEM_1YR: RetentionRule(
        RetentionPolicy.SYSTEM_1YR, 365, EventCategory.ADMIN, False
    ),
}

_CATEGORY_TO_POLICY: dict[EventCategory, RetentionPolicy] = {
    EventCategory.AML: RetentionPolicy.AML_5YR,
    EventCategory.COMPLIANCE: RetentionPolicy.AML_5YR,
    EventCategory.PAYMENT: RetentionPolicy.FINANCIAL_7YR,
    EventCategory.CUSTOMER: RetentionPolicy.FINANCIAL_7YR,
    EventCategory.SYSTEM: RetentionPolicy.OPERATIONAL_3YR,
    EventCategory.AUTH: RetentionPolicy.OPERATIONAL_3YR,
    EventCategory.ADMIN: RetentionPolicy.SYSTEM_1YR,
}


class RetentionEnforcer:
    """Manages audit record retention policies with HITL-gated purge."""

    def __init__(
        self,
        event_port: EventStorePort | None = None,
        rules: dict[RetentionPolicy, RetentionRule] | None = None,
    ) -> None:
        self._events: EventStorePort = event_port or InMemoryEventStorePort()
        self._rules = DEFAULT_RULES if rules is None else rules

    def get_retention_days(self, category: EventCategory) -> int:
        """Map category → policy → days; default 1825 (5yr)."""
        policy = _CATEGORY_TO_POLICY.get(category)
        if policy is None:
            return 1825
        rule = self._rules.get(policy)
        return rule.retention_days if rule else 1825

    def schedule_purge(
        self,
        category: EventCategory,
        older_than_days: int,
    ) -> HITLProposal:
        """Purge is ALWAYS HITL — deleting audit records is irreversible (I-27)."""
        return HITLProposal(
            action="purge_audit_records",
            resource_id=f"{category.value}:{older_than_days}d",
            requires_approval_from="MLRO",
            reason=(
                f"Purge of {category.value} events older than {older_than_days} days "
                "is irreversible — requires human approval (I-27, I-08)"
            ),
            autonomy_level="L4",
        )

    def list_due_for_purge(self, as_of: datetime | None = None) -> list[dict]:
        """Return metadata of events older than their retention period (no delete)."""
        cutoff_dt = as_of or datetime.now(UTC)
        due: list[dict] = []
        all_events = self._get_all_events()
        for event in all_events:
            retention_days = self.get_retention_days(event.category)
            expiry = event.timestamp + timedelta(days=retention_days)
            if expiry < cutoff_dt:
                due.append(
                    {
                        "event_id": event.id,
                        "category": event.category.value,
                        "timestamp": event.timestamp.isoformat(),
                        "retention_days": retention_days,
                        "expired_at": expiry.isoformat(),
                    }
                )
        return due

    def _get_all_events(self) -> list[AuditEvent]:
        if hasattr(self._events, "list_all"):
            return self._events.list_all()  # type: ignore[attr-defined]
        return []

    def get_rule(self, policy: RetentionPolicy) -> RetentionRule:
        """Return retention rule for policy."""
        rule = self._rules.get(policy)
        if rule is None:
            raise KeyError(f"No rule for policy: {policy.value}")
        return rule

    def list_rules(self) -> list[RetentionRule]:
        """Return all retention rules."""
        return list(self._rules.values())
