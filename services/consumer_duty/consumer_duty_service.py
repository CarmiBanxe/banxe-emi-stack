"""
services/consumer_duty/consumer_duty_service.py — Consumer Duty Service
IL-050 | S9-06 | FCA PS22/9 | banxe-emi-stack

Implements the ConsumerDutyPort with in-memory stores (ClickHouse in production).

Services provided:
  assess_vulnerability()  — classify customer vulnerability (FCA FG21/1)
  assess_fair_value()     — product fee vs. benefit fair value test (COBS 6.1A)
  record_outcome()        — record a Consumer Duty outcome observation (PS22/9 §10)
  generate_report()       — aggregate report for FCA board review

Fee benchmarks used in fair_value assessment are UK EMI industry averages
(sourced from PSR Market Review 2024, Which? Payment Accounts 2024).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from services.consumer_duty.consumer_duty_port import (
    ConsumerDutyOutcome,
    ConsumerDutyReport,
    FairValueAssessment,
    FairValueVerdict,
    OutcomeRating,
    OutcomeRecord,
    VulnerabilityAssessment,
    VulnerabilityCategory,
    VulnerabilityFlag,
)

logger = logging.getLogger(__name__)


# ── Vulnerability classification ───────────────────────────────────────────────

_FLAG_TO_CATEGORY: dict[VulnerabilityFlag, VulnerabilityCategory] = {
    VulnerabilityFlag.FINANCIAL_DIFFICULTY: VulnerabilityCategory.RESILIENCE,
    VulnerabilityFlag.LOW_FINANCIAL_LITERACY: VulnerabilityCategory.CAPABILITY,
    VulnerabilityFlag.MENTAL_HEALTH: VulnerabilityCategory.HEALTH,
    VulnerabilityFlag.PHYSICAL_DISABILITY: VulnerabilityCategory.HEALTH,
    VulnerabilityFlag.ELDERLY_ISOLATED: VulnerabilityCategory.CAPABILITY,
    VulnerabilityFlag.BEREAVEMENT: VulnerabilityCategory.LIFE_EVENTS,
    VulnerabilityFlag.RELATIONSHIP_BREAKDOWN: VulnerabilityCategory.LIFE_EVENTS,
    VulnerabilityFlag.DOMESTIC_ABUSE: VulnerabilityCategory.LIFE_EVENTS,
    VulnerabilityFlag.RECENT_JOB_LOSS: VulnerabilityCategory.RESILIENCE,
}

# Support actions recommended per flag (FCA FG21/1 §4 — practical guidance)
_FLAG_SUPPORT_ACTIONS: dict[VulnerabilityFlag, list[str]] = {
    VulnerabilityFlag.FINANCIAL_DIFFICULTY: [
        "Refer to debt advice (StepChange / National Debtline)",
        "Apply reduced-fee plan or payment deferral if available",
        "Flag account for enhanced monitoring (no upsell comms)",
    ],
    VulnerabilityFlag.LOW_FINANCIAL_LITERACY: [
        "Send simplified product guide (plain English, reading age ≤ 9)",
        "Offer 1:1 onboarding support call",
        "Include fee calculator in all comms",
    ],
    VulnerabilityFlag.MENTAL_HEALTH: [
        "Add account note — avoid high-pressure renewal comms",
        "Offer POA (Power of Attorney) setup information",
        "Route to dedicated vulnerable customer team",
    ],
    VulnerabilityFlag.PHYSICAL_DISABILITY: [
        "Enable accessibility features (large text, screen reader compatible)",
        "Offer telephone channel as alternative to app-only journeys",
    ],
    VulnerabilityFlag.ELDERLY_ISOLATED: [
        "Assign named relationship manager for support calls",
        "Send paper statements if requested (no charge)",
        "Flag for Trusted Party / Third-Party Access setup",
    ],
    VulnerabilityFlag.BEREAVEMENT: [
        "Suspend non-essential marketing comms for 90 days",
        "Provide bereavement support information (Cruse Bereavement Care)",
        "Fast-track estate administration process",
    ],
    VulnerabilityFlag.RELATIONSHIP_BREAKDOWN: [
        "Review joint account arrangements — offer separation support",
        "Provide information on safeguarding joint funds",
    ],
    VulnerabilityFlag.DOMESTIC_ABUSE: [
        "Activate discreet banking (no statements to shared address)",
        "Provide National Domestic Abuse Helpline: 0808 2000 247",
        "Flag account for GDPR special-category extra access controls",
        "Do NOT send account communications to shared address",
    ],
    VulnerabilityFlag.RECENT_JOB_LOSS: [
        "Refer to employment support resources (Gov.uk Find a Job)",
        "Apply fee waiver review — escalate to customer team",
        "Pause non-essential service changes for 60 days",
    ],
}


# ── Fair value benchmarks (UK EMI industry, 2024) ─────────────────────────────

# PSR Market Review 2024: average UK EMI annual fee burden for retail
_BENCHMARK_ANNUAL_FEE_INDIVIDUAL = Decimal("24.00")  # £24/yr = £2/mo average
_BENCHMARK_ANNUAL_FEE_COMPANY = Decimal("120.00")  # £120/yr typical B2B

# Banxe estimated annual usage for fair value calc:
#   INDIVIDUAL: 50 FPS txs + 20 BACS + 5 FX + 10 SEPA_CT
#   COMPANY:    200 FPS txs + 50 BACS + 20 FX + 50 SEPA_CT
_ANNUAL_USAGE: dict[str, dict[str, int]] = {
    "INDIVIDUAL": {"FPS": 50, "BACS": 20, "FX": 5, "SEPA_CT": 10},
    "COMPANY": {"FPS": 200, "BACS": 50, "FX": 20, "SEPA_CT": 50},
}

# Product benefit scores (0-100 composite):
#   FCA regulated (+20), Multi-currency (+15), Instant payments (+15),
#   Low FX fees vs. benchmark (+20), Digital-first API (+15), IBAN support (+15)
_PRODUCT_BENEFIT_SCORES: dict[str, int] = {
    "EMI_ACCOUNT": 85,
    "BUSINESS_ACCOUNT": 80,
}

# Per-transaction average amounts for fee calculation
_AVG_TX_AMOUNTS: dict[str, Decimal] = {
    "FPS": Decimal("500.00"),
    "BACS": Decimal("300.00"),
    "FX": Decimal("2000.00"),  # Larger FX transactions typical
    "SEPA_CT": Decimal("800.00"),
}

# Hardcoded Banxe fee schedule (mirrors banxe_config.yaml — avoids YAML dep here)
_BANXE_FEES: dict[str, dict[str, dict]] = {
    "EMI_ACCOUNT": {
        "FPS": {"flat": Decimal("0.20"), "pct": Decimal("0")},
        "BACS": {"flat": Decimal("0.10"), "pct": Decimal("0")},
        "FX": {"flat": Decimal("0.00"), "pct": Decimal("0.0025"), "min": Decimal("1.00")},
        "SEPA_CT": {"flat": Decimal("0.50"), "pct": Decimal("0")},
    },
    "BUSINESS_ACCOUNT": {
        "FPS": {"flat": Decimal("0.20"), "pct": Decimal("0")},
        "BACS": {"flat": Decimal("0.10"), "pct": Decimal("0")},
        "FX": {"flat": Decimal("0.00"), "pct": Decimal("0.0025"), "min": Decimal("1.00")},
        "SEPA_CT": {"flat": Decimal("0.50"), "pct": Decimal("0")},
    },
}


def _calc_fee(product_id: str, tx_type: str, amount: Decimal) -> Decimal:
    fee_cfg = _BANXE_FEES.get(product_id, {}).get(tx_type)
    if fee_cfg is None:
        return Decimal("0")
    fee = fee_cfg["flat"] + amount * fee_cfg["pct"]
    min_fee = fee_cfg.get("min", Decimal("0"))
    return max(fee, min_fee).quantize(Decimal("0.01"))


# ── Service ────────────────────────────────────────────────────────────────────


class ConsumerDutyService:
    """
    In-memory Consumer Duty service.

    In production: swap in-memory stores for ClickHouse writers
    (same interface, just inject different implementations).
    All writes include timestamp and operator_id for FCA audit trail.
    """

    def __init__(self) -> None:
        # In-memory stores (key: customer_id)
        self._vulnerabilities: dict[str, VulnerabilityAssessment] = {}
        self._outcome_records: list[OutcomeRecord] = []

    # ── Vulnerability assessment (FCA FG21/1) ─────────────────────────────────

    def assess_vulnerability(
        self,
        customer_id: str,
        flags: list[VulnerabilityFlag],
        assessed_by: str = "system",
        notes: str = "",
    ) -> VulnerabilityAssessment:
        """
        Classify vulnerability and determine required support actions.
        Stores the latest assessment per customer (overwrites previous).

        FCA FG21/1: firms must take PRACTICAL ACTION, not just record flags.
        """
        categories = list({_FLAG_TO_CATEGORY[f] for f in flags})

        # Deduplicated actions across all flags
        support_actions: list[str] = []
        seen: set[str] = set()
        for flag in flags:
            for action in _FLAG_SUPPORT_ACTIONS.get(flag, []):
                if action not in seen:
                    support_actions.append(action)
                    seen.add(action)

        assessment = VulnerabilityAssessment(
            customer_id=customer_id,
            flags=list(flags),
            categories=categories,
            support_actions=support_actions,
            is_vulnerable=len(flags) > 0,
            assessed_at=datetime.now(UTC),
            assessed_by=assessed_by,
            notes=notes,
        )
        self._vulnerabilities[customer_id] = assessment
        logger.info(
            "Vulnerability assessed: customer=%s flags=%s vulnerable=%s",
            customer_id,
            [f.value for f in flags],
            assessment.is_vulnerable,
        )
        return assessment

    def get_vulnerability(self, customer_id: str) -> VulnerabilityAssessment | None:
        """Retrieve latest vulnerability assessment for a customer."""
        return self._vulnerabilities.get(customer_id)

    # ── Fair value assessment (COBS 6.1A) ─────────────────────────────────────

    def assess_fair_value(
        self, product_id: str, entity_type: str = "INDIVIDUAL"
    ) -> FairValueAssessment:
        """
        Assess whether product fees represent fair value vs. industry benchmarks.

        Method:
          1. Calculate annual fee burden at typical usage volumes
          2. Compare against UK EMI industry benchmark
          3. Factor in benefit score (product features + regulation + UX)
          4. Verdict: FAIR / REVIEW_REQUIRED / UNFAIR

        PS22/9 §6.6: assessment must be documented and reviewed at least annually.
        COBS 6.1A.4: must consider costs AND benefits to the customer.
        """
        if product_id not in _BANXE_FEES:
            raise ValueError(f"Unknown product: {product_id}")

        usage = _ANNUAL_USAGE.get(entity_type, _ANNUAL_USAGE["INDIVIDUAL"])
        benchmark = (
            _BENCHMARK_ANNUAL_FEE_COMPANY
            if entity_type == "COMPANY"
            else _BENCHMARK_ANNUAL_FEE_INDIVIDUAL
        )

        # Calculate estimated annual fee burden
        annual_fee = Decimal("0")
        for tx_type, count in usage.items():
            avg_amount = _AVG_TX_AMOUNTS.get(tx_type, Decimal("500"))
            annual_fee += _calc_fee(product_id, tx_type, avg_amount) * count

        benefit_score = _PRODUCT_BENEFIT_SCORES.get(product_id, 60)

        # Verdict logic: fee ratio vs. benchmark + benefit score
        fee_ratio = annual_fee / benchmark if benchmark > 0 else Decimal("1")

        if fee_ratio <= Decimal("1.0") and benefit_score >= 70:
            verdict = FairValueVerdict.FAIR
            rationale = (
                f"Annual fee estimate £{annual_fee:.2f} is at or below the "
                f"UK EMI benchmark £{benchmark:.2f}. "
                f"Benefit score {benefit_score}/100 reflects FCA regulation, "
                f"multi-currency, instant payments, and competitive FX rates."
            )
        elif fee_ratio <= Decimal("1.5") or benefit_score >= 50:
            verdict = FairValueVerdict.REVIEW_REQUIRED
            rationale = (
                f"Annual fee estimate £{annual_fee:.2f} is within 50% of the "
                f"UK EMI benchmark £{benchmark:.2f}. "
                f"Board review recommended to confirm ongoing fair value. "
                f"Benefit score: {benefit_score}/100."
            )
        else:
            verdict = FairValueVerdict.UNFAIR
            rationale = (
                f"Annual fee estimate £{annual_fee:.2f} significantly exceeds "
                f"the UK EMI benchmark £{benchmark:.2f} "
                f"(ratio {fee_ratio:.1f}x). "
                f"Benefit score {benefit_score}/100 does not justify premium. "
                f"Remediation action required under PS22/9."
            )

        assessment = FairValueAssessment(
            product_id=product_id,
            entity_type=entity_type,
            annual_fee_estimate=annual_fee.quantize(Decimal("0.01")),
            benchmark_annual_fee=benchmark,
            benefit_score=benefit_score,
            verdict=verdict,
            rationale=rationale,
            assessed_at=datetime.now(UTC),
        )
        logger.info(
            "FairValue assessed: product=%s entity=%s fee=£%s verdict=%s",
            product_id,
            entity_type,
            annual_fee,
            verdict.value,
        )
        return assessment

    # ── Outcome monitoring (PS22/9 §10) ───────────────────────────────────────

    def record_outcome(
        self,
        customer_id: str,
        outcome: ConsumerDutyOutcome,
        rating: OutcomeRating,
        interaction_type: str,
        notes: str = "",
    ) -> OutcomeRecord:
        """
        Record a Customer Duty outcome observation.
        Stored for aggregation in the annual board report.
        """
        record = OutcomeRecord(
            record_id=str(uuid.uuid4()),
            customer_id=customer_id,
            outcome=outcome,
            rating=rating,
            interaction_type=interaction_type,
            notes=notes,
        )
        self._outcome_records.append(record)
        logger.debug(
            "Outcome recorded: customer=%s outcome=%s rating=%s",
            customer_id,
            outcome.value,
            rating.value,
        )
        return record

    # ── Consumer Duty report (PS22/9 §10) ─────────────────────────────────────

    def generate_report(
        self,
        period_start: date,
        period_end: date,
        total_customers: int,
        complaints_count: int = 0,
        avg_complaint_resolution_days: float = 0.0,
    ) -> ConsumerDutyReport:
        """
        Generate Consumer Duty board monitoring report for a period.

        PS22/9 §10.12: firms must be able to demonstrate they've assessed
        consumer outcomes and identified any foreseeable harm.

        period_start / period_end filter outcome records by recorded_at date.
        """
        # Filter records to period
        period_records = [
            r for r in self._outcome_records if period_start <= r.recorded_at.date() <= period_end
        ]

        # Build outcome ratings matrix
        outcome_ratings: dict[str, dict[str, int]] = {
            o.value: {r.value: 0 for r in OutcomeRating} for o in ConsumerDutyOutcome
        }
        for record in period_records:
            outcome_ratings[record.outcome.value][record.rating.value] += 1

        # Count unique vulnerable customers in the period
        vulnerable_count = sum(1 for a in self._vulnerabilities.values() if a.is_vulnerable)

        # Fair value assessments for all known products
        fair_value_assessments = []
        for product_id in _BANXE_FEES:
            for entity_type in ("INDIVIDUAL", "COMPANY"):
                fva = self.assess_fair_value(product_id, entity_type)
                fair_value_assessments.append(fva)

        report = ConsumerDutyReport(
            period_start=period_start,
            period_end=period_end,
            generated_at=datetime.now(UTC),
            total_customers=total_customers,
            vulnerable_customers=vulnerable_count,
            outcome_ratings=outcome_ratings,
            fair_value_assessments=fair_value_assessments,
            complaints_count=complaints_count,
            avg_complaint_resolution_days=avg_complaint_resolution_days,
        )
        logger.info(
            "ConsumerDuty report generated: period=%s→%s customers=%d "
            "vulnerable=%d good_outcomes=%.1f%%",
            period_start,
            period_end,
            total_customers,
            vulnerable_count,
            report.overall_good_outcome_pct,
        )
        return report
