"""
services/experiment_copilot/agents/experiment_steward.py — Experiment Steward
IL-CEC-01 | banxe-emi-stack

Reviews draft experiments for completeness, approves or rejects them,
and generates weekly summary reports.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from services.experiment_copilot.models.experiment import (
    ApproveRequest,
    ComplianceExperiment,
    ExperimentStatus,
    ExperimentSummary,
    RejectRequest,
)
from services.experiment_copilot.store.audit_trail import AuditTrail
from services.experiment_copilot.store.experiment_store import ExperimentStore

logger = logging.getLogger("banxe.experiment_copilot.steward")


class ValidationError(Exception):
    """Raised when an experiment fails steward validation."""


class ExperimentSteward:
    """Reviews and approves/rejects compliance experiments.

    Validation rules (must ALL pass for approval):
    - Hypothesis must be at least 20 characters
    - At least 1 KB citation required
    - Metrics baseline and target must be non-empty
    - No conflicting active experiments with same scope

    HITL invariant: steward actions are logged to audit trail.
    """

    def __init__(self, store: ExperimentStore, audit: AuditTrail) -> None:
        self._store = store
        self._audit = audit

    def validate(self, experiment: ComplianceExperiment) -> list[str]:
        """Return list of validation errors. Empty list = valid."""
        errors: list[str] = []

        if len(experiment.hypothesis.strip()) < 20:
            errors.append("Hypothesis must be at least 20 characters")

        if not experiment.kb_citations:
            errors.append("At least 1 KB citation is required")

        if not experiment.metrics_baseline:
            errors.append("metrics_baseline must be non-empty")

        if not experiment.metrics_target:
            errors.append("metrics_target must be non-empty")

        if experiment.status != ExperimentStatus.DRAFT:
            errors.append(f"Can only validate DRAFT experiments, got: {experiment.status.value}")

        return errors

    def approve(self, experiment_id: str, request: ApproveRequest) -> ComplianceExperiment:
        """Approve a DRAFT experiment → moves to ACTIVE.

        Args:
            experiment_id: ID of the experiment to approve.
            request: ApproveRequest with optional steward notes.

        Returns:
            Updated experiment in ACTIVE status.

        Raises:
            ValueError: If experiment not found.
            ValidationError: If experiment fails validation checks.
        """
        exp = self._store.get(experiment_id)
        if exp is None:
            raise ValueError(f"Experiment '{experiment_id}' not found")

        errors = self.validate(exp)
        if errors:
            raise ValidationError(
                f"Experiment '{experiment_id}' failed validation: {'; '.join(errors)}"
            )

        # Check for scope conflicts with active experiments
        conflicts = self._find_scope_conflicts(exp)
        if conflicts:
            logger.warning(
                "Approving experiment %s despite scope conflicts: %s",
                experiment_id,
                [c.id for c in conflicts],
            )

        exp.status = ExperimentStatus.ACTIVE
        exp.steward_notes = request.steward_notes
        self._store.save(exp)

        self._audit.log(
            actor="steward",
            action="experiment.approved",
            experiment_id=experiment_id,
            details={
                "notes": request.steward_notes,
                "conflicts": [c.id for c in conflicts],
            },
        )
        logger.info("Approved experiment %s", experiment_id)
        return exp

    def reject(self, experiment_id: str, request: RejectRequest) -> ComplianceExperiment:
        """Reject a DRAFT experiment → moves to REJECTED.

        Args:
            experiment_id: ID of the experiment to reject.
            request: RejectRequest with mandatory reason.

        Returns:
            Updated experiment in REJECTED status.

        Raises:
            ValueError: If experiment not found or not in DRAFT status.
        """
        exp = self._store.get(experiment_id)
        if exp is None:
            raise ValueError(f"Experiment '{experiment_id}' not found")
        if exp.status != ExperimentStatus.DRAFT:
            raise ValueError(f"Can only reject DRAFT experiments, got: {exp.status.value}")

        exp.status = ExperimentStatus.REJECTED
        exp.rejection_reason = request.reason
        self._store.save(exp)

        self._audit.log(
            actor="steward",
            action="experiment.rejected",
            experiment_id=experiment_id,
            details={"reason": request.reason},
        )
        logger.info("Rejected experiment %s: %s", experiment_id, request.reason)
        return exp

    def finish(self, experiment_id: str, notes: str = "") -> ComplianceExperiment:
        """Mark an ACTIVE experiment as FINISHED."""
        exp = self._store.get(experiment_id)
        if exp is None:
            raise ValueError(f"Experiment '{experiment_id}' not found")
        if exp.status != ExperimentStatus.ACTIVE:
            raise ValueError(f"Can only finish ACTIVE experiments, got: {exp.status.value}")

        exp.status = ExperimentStatus.FINISHED
        exp.steward_notes = (exp.steward_notes or "") + f"\n[Finished] {notes}".strip()
        self._store.save(exp)

        self._audit.log(
            actor="steward",
            action="experiment.finished",
            experiment_id=experiment_id,
            details={"notes": notes},
        )
        logger.info("Finished experiment %s", experiment_id)
        return exp

    def generate_weekly_report(self) -> str:
        """Generate a markdown weekly summary of experiment activity."""
        now = datetime.utcnow()
        week_ago = now - timedelta(days=7)

        all_experiments = self._store.list_all()
        recent = [s for s in all_experiments if s.updated_at >= week_ago]

        counts = self._store.count_by_status()
        lines = [
            "# Compliance Experiment Weekly Report",
            f"_Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}_",
            "",
            "## Summary",
            f"- Total experiments: {sum(counts.values())}",
            f"- Draft: {counts.get('draft', 0)}",
            f"- Active: {counts.get('active', 0)}",
            f"- Finished: {counts.get('finished', 0)}",
            f"- Rejected: {counts.get('rejected', 0)}",
            "",
            f"## Activity This Week ({len(recent)} experiments updated)",
        ]

        for summary in recent[:20]:
            lines.append(
                f"- [{summary.status.value.upper()}] **{summary.title}** "
                f"(`{summary.id}`) — {summary.scope.value}"
            )

        return "\n".join(lines)

    # ── Internal ───────────────────────────────────────────────────────────

    def _find_scope_conflicts(self, experiment: ComplianceExperiment) -> list[ExperimentSummary]:
        """Find active experiments with the same scope."""
        active = self._store.list_by_status(ExperimentStatus.ACTIVE)
        return [s for s in active if s.scope == experiment.scope]
