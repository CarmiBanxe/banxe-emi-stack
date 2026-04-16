"""
services/compliance_automation/compliance_automation_agent.py
IL-CAE-01 | Phase 23

ComplianceAutomationAgent — orchestrates rule evaluation, breach detection,
remediation tracking, and policy management.

HITL gate: FCA breach reporting requires Compliance Officer approval (I-27, L4).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from services.compliance_automation.breach_reporter import BreachReporter
from services.compliance_automation.models import RuleType
from services.compliance_automation.periodic_review import PeriodicReview
from services.compliance_automation.policy_manager import PolicyManager
from services.compliance_automation.remediation_tracker import RemediationTracker
from services.compliance_automation.rule_engine import RuleEngine


class ComplianceAutomationAgent:
    """Orchestrates all compliance automation components."""

    def __init__(
        self,
        rule_engine: RuleEngine,
        policy_manager: PolicyManager,
        periodic_review: PeriodicReview,
        breach_reporter: BreachReporter,
        remediation_tracker: RemediationTracker,
    ) -> None:
        self._rule_engine = rule_engine
        self._policy_manager = policy_manager
        self._periodic_review = periodic_review
        self._breach_reporter = breach_reporter
        self._remediation_tracker = remediation_tracker

    async def evaluate_compliance(
        self,
        entity_id: str,
        rule_ids: list[str] | None = None,
    ) -> dict:
        """Evaluate entity against active rules, detect breaches, return summary."""
        checks = await self._rule_engine.evaluate_entity(entity_id, rule_ids)
        breaches = await self._breach_reporter.detect_breaches(entity_id, checks)

        statuses = [c.status.value for c in checks]
        if "FAIL" in statuses:
            overall = "FAIL"
        elif "WARNING" in statuses:
            overall = "WARNING"
        else:
            overall = "PASS"

        return {
            "checks": [
                {
                    "check_id": c.check_id,
                    "rule_id": c.rule_id,
                    "status": c.status.value,
                    "finding": c.finding,
                    "checked_at": c.checked_at.isoformat(),
                }
                for c in checks
            ],
            "breaches": [
                {
                    "breach_id": b.breach_id,
                    "rule_id": b.rule_id,
                    "severity": b.severity.value,
                    "description": b.description,
                    "detected_at": b.detected_at.isoformat(),
                }
                for b in breaches
            ],
            "overall_status": overall,
        }

    async def get_rules(self, rule_type: str | None = None) -> list[dict]:
        """Return active compliance rules, optionally filtered by type string."""
        rt: RuleType | None = None
        if rule_type is not None:
            rt = RuleType(rule_type)
        rules = await self._rule_engine.get_rules(rt)
        return [
            {
                "rule_id": r.rule_id,
                "name": r.name,
                "rule_type": r.rule_type.value,
                "severity": r.severity.value,
                "description": r.description,
                "is_active": r.is_active,
                "version": r.version,
            }
            for r in rules
        ]

    async def report_breach(self, breach_id: str, actor: str) -> dict:
        """HITL L4: FCA submission always requires Compliance Officer approval."""
        return {
            "status": "HITL_REQUIRED",
            "reason": "FCA breach reporting requires Compliance Officer approval",
        }

    async def track_remediation(
        self,
        check_id: str,
        entity_id: str,
        finding: str,
        assigned_to: str,
        due_days: int = 30,
    ) -> dict:
        """Create a remediation item for a compliance finding."""
        due_date = datetime.now(UTC) + timedelta(days=due_days)
        remediation = await self._remediation_tracker.create_remediation(
            check_id=check_id,
            entity_id=entity_id,
            finding=finding,
            assigned_to=assigned_to,
            due_date=due_date,
        )
        return {
            "remediation_id": remediation.remediation_id,
            "check_id": remediation.check_id,
            "entity_id": remediation.entity_id,
            "finding": remediation.finding,
            "status": remediation.status.value,
            "assigned_to": remediation.assigned_to,
            "due_date": remediation.due_date.isoformat(),
        }

    async def get_policy_diff(self, policy_id: str, v1: int, v2: int) -> dict:
        """Return content diff between two policy versions."""
        return await self._policy_manager.diff_versions(policy_id, v1, v2)

    async def create_policy(
        self,
        policy_id: str,
        content: str,
        author: str,
    ) -> dict:
        """Create a new policy in DRAFT state."""
        version = await self._policy_manager.create_policy(policy_id, content, author)
        return {
            "version_id": version.version_id,
            "policy_id": version.policy_id,
            "version_number": version.version_number,
            "status": version.status.value,
            "author": version.author,
            "created_at": version.created_at.isoformat(),
        }
