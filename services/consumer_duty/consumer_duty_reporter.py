"""
services/consumer_duty/consumer_duty_reporter.py
Consumer Duty Reporter
IL-CDO-01 | Phase 50 | Sprint 35

FCA: PS22/9 Consumer Duty Annual Assessment (s.1.4), FCA PRIN 12
Trust Zone: AMBER

generate_annual_report — stub: NotImplementedError (BT-005).
generate_outcome_dashboard — 4 outcome areas, vulnerability counts.
export_board_report — always HITLProposal (I-27: L4, CFO approval).
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging

from services.consumer_duty.models_v2 import (
    AssessmentStatus,
    HITLProposal,
    InMemoryOutcomeStore,
    InMemoryProductGovernance,
    InMemoryVulnerabilityAlertStore,
    OutcomeStorePort,
    OutcomeType,
    ProductGovernancePort,
    VulnerabilityAlertPort,
    VulnerabilityFlag,
)

logger = logging.getLogger(__name__)


class ConsumerDutyReporter:
    """Consumer Duty reporter (PS22/9).

    Protocol DI: OutcomeStorePort, ProductGovernancePort, VulnerabilityAlertPort.
    I-27: Board report export always L4 HITL (CFO approval).
    BT-005: Annual report is a stub pending integration.
    """

    def __init__(
        self,
        outcome_store: OutcomeStorePort | None = None,
        governance_store: ProductGovernancePort | None = None,
        alert_store: VulnerabilityAlertPort | None = None,
    ) -> None:
        """Initialise with injectable stores (default: InMemory stubs)."""
        self._outcomes: OutcomeStorePort = outcome_store or InMemoryOutcomeStore()
        self._governance: ProductGovernancePort = governance_store or InMemoryProductGovernance()
        self._alerts: VulnerabilityAlertPort = alert_store or InMemoryVulnerabilityAlertStore()

    def generate_annual_report(self, year: int) -> dict[str, object]:
        """Generate Consumer Duty Annual Assessment (PS22/9 s.1.4).

        BT-005: Stub pending integration with reporting data warehouse.

        Args:
            year: Assessment year (e.g. 2026).

        Raises:
            NotImplementedError: BT-005 — pending integration.
        """
        raise NotImplementedError("BT-005 Consumer Duty Annual Report — pending integration")

    def generate_outcome_dashboard(self) -> dict[str, object]:
        """Generate outcome monitoring dashboard (PS22/9 §10).

        Covers all 4 outcome areas with failing counts and vulnerability counts.

        Returns:
            Dict with outcome area stats, vulnerability counts, failing products.
        """
        ts = datetime.now(UTC).isoformat()

        # Aggregate by outcome type
        outcome_stats: dict[str, object] = {}
        total_failing = 0
        for outcome_type in OutcomeType:
            assessments = self._outcomes.list_by_outcome_type(outcome_type)
            failing = [a for a in assessments if a.status == AssessmentStatus.FAILED]
            outcome_stats[str(outcome_type)] = {
                "total": len(assessments),
                "failing": len(failing),
                "passing": len(assessments) - len(failing),
            }
            total_failing += len(failing)

        # Vulnerability counts
        unreviewed_alerts = self._alerts.list_unreviewed()
        vuln_counts: dict[str, int] = {flag: 0 for flag in VulnerabilityFlag}
        for alert in unreviewed_alerts:
            vuln_counts[str(alert.vulnerability_flag)] = (
                vuln_counts.get(str(alert.vulnerability_flag), 0) + 1
            )

        # Failing products
        failing_products = self._governance.list_failing()

        return {
            "generated_at": ts,
            "outcome_areas": outcome_stats,
            "total_failing_outcomes": total_failing,
            "unreviewed_vulnerability_alerts": len(unreviewed_alerts),
            "vulnerability_breakdown": vuln_counts,
            "failing_products_count": len(failing_products),
            "failing_products": [
                {
                    "product_id": r.product_id,
                    "product_name": r.product_name,
                    "fair_value_score": str(r.fair_value_score),
                    "intervention": str(r.intervention_type),
                }
                for r in failing_products
            ],
        }

    def export_board_report(self, operator: str) -> HITLProposal:
        """Export board report — always HITLProposal (I-27: L4, CFO approval).

        PS22/9 s.5: Board must review Consumer Duty annual assessment.
        I-27: Board report export always requires CFO approval.

        Args:
            operator: Requesting operator.

        Returns:
            HITLProposal requiring CFO approval.
        """
        logger.warning(
            "Board report export requested operator=%s — HITL required (I-27)",
            operator,
        )
        return HITLProposal(
            action="EXPORT_BOARD_REPORT",
            entity_id=operator,
            requires_approval_from="CFO",
            reason=(
                f"Consumer Duty board report export requires CFO sign-off "
                f"(I-27, PS22/9 s.5): operator={operator}"
            ),
        )
