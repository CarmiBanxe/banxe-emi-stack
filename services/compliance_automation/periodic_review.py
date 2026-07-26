"""
services/compliance_automation/periodic_review.py
IL-CAE-01 | Phase 23

Periodic compliance reviews — customer KYC/AML, PEP re-screening, sanctions screening.
Generates ComplianceReport with overall_status derived from individual checks.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import os
from typing import TYPE_CHECKING
from uuid import uuid4

from services.adverse_media.models import ScreeningAction
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

if TYPE_CHECKING:
    from services.adverse_media.service import AdverseMediaService

_ANNUAL_REVIEW_DAYS = 365
_PEP_REVIEW_DAYS = 180
_SANCTIONS_REVIEW_DAYS = 1
# SANDBOX default cadence for adverse-media re-screening (MLR 2017 Reg.28 ongoing
# monitoring). Tune at prod cutover with Compliance/MLRO sign-off.
_ADVERSE_MEDIA_REVIEW_DAYS = 90
_ADVERSE_MEDIA_RULE_ID = "rule-adverse-media-001"


class PeriodicReview:
    """Runs scheduled compliance reviews and emits ComplianceReports."""

    def __init__(
        self,
        rule_store: RuleStorePort,
        check_store: CheckStorePort,
        report_store: ReportStorePort,
        *,
        adverse_media: AdverseMediaService | None = None,
    ) -> None:
        self._rule_store = rule_store
        self._check_store = check_store
        self._report_store = report_store
        self._engine = RuleEngine(rule_store, check_store)
        self._adverse_media = adverse_media

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

    async def run_adverse_media_screening(self, entity_id: str) -> ComplianceReport:
        """Periodic adverse-media re-screening (MLR 2017 Reg.28 ongoing monitoring).

        ⚠️ SANDBOX / NON-PROD — NOT USED in sandbox:
            Gated OFF by default. Unless ADVERSE_MEDIA_PERIODIC_ENABLED=1 is set in
            env, this method performs NO feed call and returns a report with a single
            SKIPPED check. PROD enablement requires, separately: Compliance/MLRO
            sign-off, a UK-GDPR lawful-basis assessment, and ADR ratification of the
            adverse-media framework. The underlying feeds (CompositeFeed nodes) keep
            their own independent SANDBOX-off env gates.

        Two-stage chain (agent-authority.md — do not violate): this periodic run is
        STAGE-1 RESEARCH, commanded by the CDD Review Agent (human double: Compliance
        Officer). It is advisory only — a hit NEVER auto-fails/auto-blocks here; the
        AdverseMediaService itself enqueues the MANDATORY MLRO HITL review (STAGE-2
        decision, L4 human). This method only records the advisory outcome as a
        ComplianceCheck (CLEAR → PASS, HITL_REVIEW → WARNING) in the report.
        """
        if os.environ.get("ADVERSE_MEDIA_PERIODIC_ENABLED", "") != "1":
            check = ComplianceCheck(
                check_id=str(uuid4()),
                entity_id=entity_id,
                rule_id=_ADVERSE_MEDIA_RULE_ID,
                status=CheckStatus.SKIPPED,
                finding="adverse_media periodic disabled (sandbox)",
                evidence=(
                    "ADVERSE_MEDIA_PERIODIC_ENABLED != 1 — no feed call performed. "
                    "Prod enablement requires Compliance/MLRO sign-off + GDPR "
                    "lawful-basis + ADR ratification."
                ),
                checked_at=datetime.now(UTC),
                checked_by="cdd_review_agent",
            )
            return await self.generate_report(entity_id, [check])

        service = self._adverse_media_service()
        # screen_customer is SYNC (feeds, matcher, HITL enqueue) — run it off-loop.
        result = await asyncio.to_thread(
            service.screen_customer, entity_id, actor_id="cdd_review_agent:periodic"
        )
        if result.action is ScreeningAction.CLEAR:
            status = CheckStatus.PASS
            finding = "Adverse-media re-screen clear"
            evidence = f"screened_at={result.screened_at.isoformat()}; risk={result.risk}"
        else:
            # Advisory WARNING only — the block/clear decision belongs to the MLRO
            # HITL case already enqueued by AdverseMediaService (no auto-fail here).
            status = CheckStatus.WARNING
            finding = (
                f"Adverse-media hit(s): {len(result.hits)} — "
                "MLRO HITL review enqueued (advisory, no auto-block)"
            )
            evidence = (
                f"screened_at={result.screened_at.isoformat()}; risk={result.risk}; "
                f"hitl_case_id={result.hitl_case_id}; marble_case_id={result.marble_case_id}"
            )
        check = ComplianceCheck(
            check_id=str(uuid4()),
            entity_id=entity_id,
            rule_id=_ADVERSE_MEDIA_RULE_ID,
            status=status,
            finding=finding,
            evidence=evidence,
            checked_at=datetime.now(UTC),
            checked_by="cdd_review_agent",
        )
        return await self.generate_report(entity_id, [check])

    def _adverse_media_service(self) -> AdverseMediaService:
        """Lazy default build — mirrors the store-injection style (env at call time).

        Injects the full CompositeFeed (agent-authority.md Stage-1 research feed);
        every node is itself SANDBOX-off by env, so the default build stays inert.
        """
        if self._adverse_media is None:
            from services.adverse_media.composite_feed import CompositeFeed
            from services.adverse_media.feed import OpenSanctionsAdjacencyFeed
            from services.adverse_media.rss_feed import RssAdverseMediaFeed
            from services.adverse_media.service import AdverseMediaService
            from services.adverse_media.web_feed import WebSearchAdverseMediaFeed
            from services.adverse_media.x_feed import XAdverseMediaFeed
            from services.customer.customer_service import get_customer_service

            feed = CompositeFeed(
                [
                    OpenSanctionsAdjacencyFeed(),
                    XAdverseMediaFeed(),
                    RssAdverseMediaFeed(),
                    WebSearchAdverseMediaFeed(),
                ]
            )
            self._adverse_media = AdverseMediaService(
                customer_service=get_customer_service(), feed=feed
            )
        return self._adverse_media

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
