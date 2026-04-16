"""
services/compliance_automation/periodic_review.py
IL-CAE-01 | Phase 23

Periodic compliance reviews — customer KYC/AML, PEP re-screening, sanctions screening.
Generates ComplianceReport with overall_status derived from individual checks.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from services.compliance_automation.models import (
    CheckStatus,
    CheckStorePort,
    ComplianceCheck,
    ComplianceReport,
    ReportStorePort,
    RuleStorePort,
    RuleType,
)
from services.compliance_automation.rule_engine import RuleEngine

_ANNUAL_REVIEW_DAYS = 365
_PEP_REVIEW_DAYS = 180
_SANCTIONS_REVIEW_DAYS = 1


class PeriodicReview:
    """Runs scheduled compliance reviews and emits ComplianceReports."""

    def __init__(
        self,
        rule_store: RuleStorePort,
        check_store: CheckStorePort,
        report_store: ReportStorePort,
    ) -> None:
        self._rule_store = rule_store
        self._check_store = check_store
        self._report_store = report_store
        self._engine = RuleEngine(rule_store, check_store)

    async def run_customer_review(self, entity_id: str) -> ComplianceReport:
        """Run KYC + AML rule evaluation and generate a customer review report."""
        kyc_checks = await self._engine.evaluate_entity(
            entity_id,
            rule_ids=await self._rule_ids_by_type(RuleType.KYC),
        )
        aml_checks = await self._engine.evaluate_entity(
            entity_id,
            rule_ids=await self._rule_ids_by_type(RuleType.AML),
        )
        all_checks = kyc_checks + aml_checks
        return await self.generate_report(entity_id, all_checks)

    async def run_pep_screening(self, entity_id: str) -> ComplianceReport:
        """Run PEP rule evaluation and generate a PEP screening report."""
        checks = await self._engine.evaluate_entity(
            entity_id,
            rule_ids=await self._rule_ids_by_type(RuleType.PEP),
        )
        return await self.generate_report(entity_id, checks)

    async def run_sanctions_screening(self, entity_id: str) -> ComplianceReport:
        """Run SANCTIONS rule evaluation and generate a sanctions screening report."""
        checks = await self._engine.evaluate_entity(
            entity_id,
            rule_ids=await self._rule_ids_by_type(RuleType.SANCTIONS),
        )
        return await self.generate_report(entity_id, checks)

    async def generate_report(
        self,
        entity_id: str,
        checks: list[ComplianceCheck],
    ) -> ComplianceReport:
        """Generate and persist a ComplianceReport from a list of checks.

        overall_status: FAIL if any FAIL; WARNING if any WARNING; else PASS.
        """
        if any(c.status == CheckStatus.FAIL for c in checks):
            overall = CheckStatus.FAIL
        elif any(c.status == CheckStatus.WARNING for c in checks):
            overall = CheckStatus.WARNING
        else:
            overall = CheckStatus.PASS

        now = datetime.now(UTC)
        report = ComplianceReport(
            report_id=str(uuid4()),
            entity_id=entity_id,
            checks=tuple(checks),
            overall_status=overall,
            generated_at=now,
            period_start=now - timedelta(days=30),
            period_end=now,
        )
        return await self._report_store.save_report(report)

    async def _rule_ids_by_type(self, rule_type: RuleType) -> list[str]:
        """Helper: return rule_ids for a given type."""
        rules = await self._rule_store.list_rules(rule_type=rule_type, active_only=True)
        return [r.rule_id for r in rules]
