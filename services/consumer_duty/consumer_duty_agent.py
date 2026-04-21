"""
services/consumer_duty/consumer_duty_agent.py
Consumer Duty Agent
IL-CDO-01 | Phase 50 | Sprint 35

FCA: PS22/9 Consumer Duty, FCA FG21/1, FCA PRIN 12
Trust Zone: AMBER

L1 auto: get outcomes, get dashboard, detect low-risk triggers.
L2 alert: failing outcomes, SLA breaches.
L4 HITL: vulnerability updates, product withdrawal, board report export (I-27).
"""

from __future__ import annotations

from decimal import Decimal
import logging

from services.consumer_duty.consumer_duty_reporter import ConsumerDutyReporter
from services.consumer_duty.consumer_support_tracker import ConsumerSupportTracker
from services.consumer_duty.models_v2 import (
    HITLProposal,
    InMemoryOutcomeStore,
    InMemoryProductGovernance,
    InMemoryVulnerabilityAlertStore,
    OutcomeAssessment,
    OutcomeType,
    VulnerabilityAlert,
    VulnerabilityFlag,
)
from services.consumer_duty.outcome_assessor import OutcomeAssessor
from services.consumer_duty.product_governance import ProductGovernanceService
from services.consumer_duty.vulnerability_detector import VulnerabilityDetector

logger = logging.getLogger(__name__)

# L2 alert threshold: SLA breach rate > 20%
SLA_BREACH_ALERT_THRESHOLD = Decimal("0.2")


class ConsumerDutyAgent:
    """Consumer Duty Agent.

    L1 (auto): get outcomes, get dashboard, detect low-risk triggers.
    L2 (alert): failing outcomes, SLA breaches > 20%.
    L4 (HITL): vulnerability flag updates, product withdrawal, board report (I-27).

    Protocol DI: OutcomeAssessor, VulnerabilityDetector, ProductGovernanceService,
                 ConsumerDutyReporter, ConsumerSupportTracker.
    """

    AUTONOMY_LEVEL = "L4"  # Most consequential operations are L4

    def __init__(
        self,
        outcome_assessor: OutcomeAssessor | None = None,
        vulnerability_detector: VulnerabilityDetector | None = None,
        product_governance: ProductGovernanceService | None = None,
        reporter: ConsumerDutyReporter | None = None,
        support_tracker: ConsumerSupportTracker | None = None,
    ) -> None:
        """Initialise with injectable services (default: InMemory stubs)."""
        outcome_store = InMemoryOutcomeStore()
        governance_store = InMemoryProductGovernance()
        alert_store = InMemoryVulnerabilityAlertStore()

        self._assessor = outcome_assessor or OutcomeAssessor(outcome_store)
        self._detector = vulnerability_detector or VulnerabilityDetector(alert_store)
        self._governance = product_governance or ProductGovernanceService(governance_store)
        self._reporter = reporter or ConsumerDutyReporter(
            outcome_store, governance_store, alert_store
        )
        self._tracker = support_tracker or ConsumerSupportTracker()

    # ── L1 Auto operations ────────────────────────────────────────────────────

    def get_outcomes(self, customer_id: str) -> list[OutcomeAssessment]:
        """L1: Get customer outcome assessments (auto).

        Args:
            customer_id: Customer identifier.

        Returns:
            List of OutcomeAssessment records.
        """
        outcomes = self._assessor.get_customer_outcomes(customer_id)
        logger.info("L1 get_outcomes customer=%s count=%d", customer_id, len(outcomes))
        return outcomes

    def get_dashboard(self) -> dict[str, object]:
        """L1: Get outcome monitoring dashboard (auto).

        Returns:
            Dashboard dict with outcome area stats.
        """
        return self._reporter.generate_outcome_dashboard()

    def detect_vulnerability(
        self, customer_id: str, trigger: str, context: dict[str, object]
    ) -> VulnerabilityAlert | HITLProposal:
        """L1/L4: Detect vulnerability — auto for LOW/MEDIUM, HITL for HIGH/CRITICAL.

        Args:
            customer_id: Customer identifier.
            trigger: Vulnerability trigger.
            context: Context dict.

        Returns:
            VulnerabilityAlert (L1) or HITLProposal (L4).
        """
        return self._detector.detect_vulnerability(customer_id, trigger, context)

    # ── L2 Alert operations ───────────────────────────────────────────────────

    def check_failing_outcomes(
        self, outcome_type: OutcomeType | None = None
    ) -> list[OutcomeAssessment]:
        """L2: Get failing outcomes — alert for compliance team review.

        Args:
            outcome_type: Optional filter.

        Returns:
            List of failing OutcomeAssessment records.
        """
        failing = self._assessor.get_failing_outcomes(outcome_type)
        if failing:
            logger.warning(
                "L2 alert: %d failing outcomes detected type=%s",
                len(failing),
                outcome_type,
            )
        return failing

    def check_sla_breaches(self, interaction_type: str = "support") -> Decimal:
        """L2: Check SLA breach rate — alerts if above 20% threshold.

        Args:
            interaction_type: Interaction type to check.

        Returns:
            SLA breach rate as Decimal (I-01).
        """
        rate = self._tracker.get_sla_breach_rate(interaction_type)
        if rate > SLA_BREACH_ALERT_THRESHOLD:
            logger.warning(
                "L2 alert: SLA breach rate %s > threshold %s type=%s",
                rate,
                SLA_BREACH_ALERT_THRESHOLD,
                interaction_type,
            )
        return rate

    # ── L4 HITL operations ────────────────────────────────────────────────────

    def update_vulnerability_flag(self, customer_id: str, flag: VulnerabilityFlag) -> HITLProposal:
        """L4 HITL: Update vulnerability flag — returns HITLProposal (I-27).

        Args:
            customer_id: Customer identifier.
            flag: New vulnerability flag.

        Returns:
            HITLProposal requiring CONSUMER_DUTY_OFFICER approval.
        """
        logger.warning(
            "L4 update_vulnerability_flag customer=%s flag=%s — HITL required", customer_id, flag
        )
        return self._detector.update_vulnerability_flag(customer_id, flag)

    def propose_product_withdrawal(
        self, product_id: str, reason: str, operator: str
    ) -> HITLProposal:
        """L4 HITL: Propose product withdrawal — returns HITLProposal (I-27).

        Args:
            product_id: Product to withdraw.
            reason: Withdrawal reason.
            operator: Requesting operator.

        Returns:
            HITLProposal requiring CONSUMER_DUTY_OFFICER approval.
        """
        logger.warning("L4 propose_product_withdrawal product_id=%s — HITL required", product_id)
        return self._governance.propose_product_withdrawal(product_id, reason, operator)

    def export_board_report(self, operator: str) -> HITLProposal:
        """L4 HITL: Export board report — returns HITLProposal (I-27, CFO approval).

        Args:
            operator: Requesting operator.

        Returns:
            HITLProposal requiring CFO approval.
        """
        logger.warning("L4 export_board_report operator=%s — HITL required (CFO)", operator)
        return self._reporter.export_board_report(operator)
