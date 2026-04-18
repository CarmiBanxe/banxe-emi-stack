"""
services/risk_management/mitigation_tracker.py
IL-RMS-01 | Phase 37 | banxe-emi-stack

Mitigation Tracker — create, update, and track risk mitigation plans.
I-12: SHA-256 evidence hashing.
I-24: Append-only plan history.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
import hashlib
import uuid

from services.risk_management.models import (
    InMemoryMitigationPort,
    MitigationAction,
    MitigationPlan,
    MitigationPort,
)


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


class MitigationTracker:
    """Creates and tracks risk mitigation plans with evidence integrity."""

    def __init__(self, store: MitigationPort | None = None) -> None:
        self._store: MitigationPort = store or InMemoryMitigationPort()

    def create_plan(
        self,
        assessment_id: str,
        description: str,
        owner: str,
        due_date: datetime,
    ) -> MitigationPlan:
        """Create a new mitigation plan; initial action = IDENTIFIED."""
        evidence_hash = _sha256(assessment_id + description)
        plan = MitigationPlan(
            id=str(uuid.uuid4()),
            assessment_id=assessment_id,
            action=MitigationAction.IDENTIFIED,
            description=description,
            owner=owner,
            due_date=due_date,
            evidence_hash=evidence_hash,
            completed_at=None,
        )
        self._store.save_plan(plan)
        return plan

    def update_action(
        self,
        plan_id: str,
        action: MitigationAction,
        evidence: str | None = None,
    ) -> MitigationPlan:
        """Update mitigation action; recompute hash if evidence provided (I-12)."""
        plan = self._store.get_plan(plan_id)
        if plan is None:
            raise ValueError(f"MitigationPlan {plan_id!r} not found")

        new_hash = _sha256(evidence) if evidence else plan.evidence_hash
        completed_at = (
            datetime.now(UTC) if action == MitigationAction.MITIGATED else plan.completed_at
        )

        updated = MitigationPlan(
            id=plan.id,
            assessment_id=plan.assessment_id,
            action=action,
            description=plan.description,
            owner=plan.owner,
            due_date=plan.due_date,
            evidence_hash=new_hash,
            completed_at=completed_at,
        )
        self._store.save_plan(updated)
        return updated

    def get_plan(self, plan_id: str) -> MitigationPlan | None:
        """Return plan by ID."""
        return self._store.get_plan(plan_id)

    def list_overdue(self, as_of: date | None = None) -> list[MitigationPlan]:
        """Return plans where due_date < as_of and not yet MITIGATED or ACCEPTED."""
        cutoff = as_of or date.today()
        terminal = {MitigationAction.MITIGATED, MitigationAction.ACCEPTED}
        all_plans = self._store.list_plans("")
        return [p for p in all_plans if p.due_date.date() < cutoff and p.action not in terminal]

    def attach_evidence(self, plan_id: str, evidence: str) -> MitigationPlan:
        """Recompute SHA-256 hash with new evidence (I-12), update plan."""
        return self.update_action(plan_id, MitigationAction.IN_PROGRESS, evidence)
