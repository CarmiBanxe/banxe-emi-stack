"""
services/compliance_automation/rule_engine.py
IL-CAE-01 | Phase 23

Rule evaluation engine — loads active compliance rules, evaluates entities,
saves check results to the check store. Append-only (I-24).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from services.compliance_automation.models import (
    CheckStatus,
    CheckStorePort,
    ComplianceCheck,
    ComplianceRule,
    RuleStorePort,
    RuleType,
)


class RuleEngine:
    """Evaluates compliance rules against an entity and persists results."""

    def __init__(
        self,
        rule_store: RuleStorePort,
        check_store: CheckStorePort,
    ) -> None:
        self._rule_store = rule_store
        self._check_store = check_store

    async def evaluate_entity(
        self,
        entity_id: str,
        rule_ids: list[str] | None = None,
    ) -> list[ComplianceCheck]:
        """Evaluate all active rules (or specific rule_ids) against the entity."""
        active_rules = await self._rule_store.list_rules(active_only=True)

        if rule_ids is not None:
            active_rules = [r for r in active_rules if r.rule_id in rule_ids]

        checks: list[ComplianceCheck] = []
        for rule in active_rules:
            check = self._evaluate_rule(entity_id, rule)
            saved = await self._check_store.save_check(check)
            checks.append(saved)

        return checks

    def _evaluate_rule(self, entity_id: str, rule: ComplianceRule) -> ComplianceCheck:
        """Apply stub evaluation logic based on evaluation_logic hint."""
        logic = rule.evaluation_logic.lower()

        if "sanctions_hit" in logic:
            status = CheckStatus.FAIL
            finding = "Sanctions match detected"
            evidence = f"Rule {rule.rule_id} triggered sanctions_hit logic"
        elif "aml_threshold" in logic:
            status = CheckStatus.PASS
            finding = "AML threshold check passed"
            evidence = f"Rule {rule.rule_id} evaluated aml_threshold logic"
        elif "kyc_expired" in logic:
            status = CheckStatus.PASS
            finding = "KYC review is current"
            evidence = f"Rule {rule.rule_id} evaluated kyc_expired logic"
        else:
            status = CheckStatus.PASS
            finding = "Check passed"
            evidence = f"Rule {rule.rule_id} evaluated with default pass logic"

        return ComplianceCheck(
            check_id=str(uuid4()),
            entity_id=entity_id,
            rule_id=rule.rule_id,
            status=status,
            finding=finding,
            evidence=evidence,
            checked_at=datetime.now(UTC),
            checked_by="system",
        )

    async def get_rules(
        self,
        rule_type: RuleType | None = None,
    ) -> list[ComplianceRule]:
        """Return active rules, optionally filtered by type."""
        return await self._rule_store.list_rules(rule_type=rule_type, active_only=True)

    async def register_rule(self, rule: ComplianceRule) -> ComplianceRule:
        """Persist and return a new compliance rule."""
        return await self._rule_store.save_rule(rule)
