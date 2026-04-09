"""
services/consumer_duty/consumer_duty_port.py — Consumer Duty domain types & port
IL-050 | S9-06 | FCA PS22/9 | banxe-emi-stack

FCA Consumer Duty (PS22/9, effective 31 July 2023) requires all FCA-regulated
firms to deliver GOOD OUTCOMES for retail customers across four areas:

  1. PRODUCTS_AND_SERVICES — products meet genuine customer needs, targeted correctly
  2. PRICE_AND_VALUE      — price is proportionate to the overall benefits received
  3. CONSUMER_UNDERSTANDING — communications help customers make informed decisions
  4. CONSUMER_SUPPORT     — accessible, effective support when customers need it

Additional obligations covered here:
  - FCA FG21/1: vulnerability identification and fair treatment (VulnerabilityFlag)
  - COBS 6.1A:  fee disclosure + fair value test (FairValueAssessment)
  - DISP 1.10:  complaints audit trail feeds outcome monitoring
  - PS22/9 §10: annual Consumer Duty monitoring report to FCA board
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol

# ── Vulnerability ──────────────────────────────────────────────────────────────


class VulnerabilityCategory(str, Enum):
    """
    FCA FG21/1 §2.2 — four drivers of vulnerability.
    A customer may fall into multiple categories.
    """

    HEALTH = "HEALTH"  # Physical or mental health conditions
    LIFE_EVENTS = "LIFE_EVENTS"  # Bereavement, job loss, relationship breakdown
    RESILIENCE = "RESILIENCE"  # Low financial resilience, debt, low savings
    CAPABILITY = "CAPABILITY"  # Low knowledge, confidence, or literacy


class VulnerabilityFlag(str, Enum):
    """
    Specific vulnerability signals observed for a customer.
    Mapped to VulnerabilityCategory in ConsumerDutyService.

    GDPR note: DOMESTIC_ABUSE is special-category data — must be handled
    with extra care and appropriate access controls (Art.9 GDPR).
    """

    FINANCIAL_DIFFICULTY = "FINANCIAL_DIFFICULTY"  # RESILIENCE
    LOW_FINANCIAL_LITERACY = "LOW_FINANCIAL_LITERACY"  # CAPABILITY
    MENTAL_HEALTH = "MENTAL_HEALTH"  # HEALTH
    PHYSICAL_DISABILITY = "PHYSICAL_DISABILITY"  # HEALTH
    ELDERLY_ISOLATED = "ELDERLY_ISOLATED"  # CAPABILITY + RESILIENCE
    BEREAVEMENT = "BEREAVEMENT"  # LIFE_EVENTS
    RELATIONSHIP_BREAKDOWN = "RELATIONSHIP_BREAKDOWN"  # LIFE_EVENTS
    DOMESTIC_ABUSE = "DOMESTIC_ABUSE"  # LIFE_EVENTS (Art.9 GDPR)
    RECENT_JOB_LOSS = "RECENT_JOB_LOSS"  # RESILIENCE + LIFE_EVENTS


# ── Consumer Duty outcomes ─────────────────────────────────────────────────────


class ConsumerDutyOutcome(str, Enum):
    """The four PS22/9 outcome areas."""

    PRODUCTS_AND_SERVICES = "PRODUCTS_AND_SERVICES"
    PRICE_AND_VALUE = "PRICE_AND_VALUE"
    CONSUMER_UNDERSTANDING = "CONSUMER_UNDERSTANDING"
    CONSUMER_SUPPORT = "CONSUMER_SUPPORT"


class OutcomeRating(str, Enum):
    """Outcome quality rating for a customer interaction."""

    GOOD = "GOOD"
    NEUTRAL = "NEUTRAL"
    POOR = "POOR"


class FairValueVerdict(str, Enum):
    """
    Result of the FCA COBS 6 fair value assessment.

    FAIR:             Price is proportionate to overall benefits.
    REVIEW_REQUIRED:  Price marginally above benchmark — board review needed.
    UNFAIR:           Price significantly exceeds value delivered — action required.
    """

    FAIR = "FAIR"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    UNFAIR = "UNFAIR"


# ── Domain types ───────────────────────────────────────────────────────────────


@dataclass
class VulnerabilityAssessment:
    """
    Vulnerability assessment for one customer.
    FCA FG21/1: firms must identify vulnerability AND take practical action.
    """

    customer_id: str
    flags: list[VulnerabilityFlag]
    categories: list[VulnerabilityCategory]
    support_actions: list[str]  # Concrete steps taken (e.g. simplified comms)
    is_vulnerable: bool
    assessed_at: datetime
    assessed_by: str  # operator_id or "system"
    notes: str = ""


@dataclass(frozen=True)
class FairValueAssessment:
    """
    Product-level fair value assessment (COBS 6.1A).

    Compares fee burden against industry benchmarks and benefit score.
    Must be reviewed at least annually and presented to the FCA board (PS22/9 §10).
    """

    product_id: str
    entity_type: str  # INDIVIDUAL | COMPANY
    annual_fee_estimate: Decimal  # Estimated annual fee at average usage (GBP)
    benchmark_annual_fee: Decimal  # Industry benchmark for comparison
    benefit_score: int  # 0-100 composite (features / value / regulation)
    verdict: FairValueVerdict
    rationale: str
    assessed_at: datetime


@dataclass
class OutcomeRecord:
    """
    Single customer outcome observation.
    Forms the dataset for the annual Consumer Duty board report (PS22/9 §10).
    """

    record_id: str
    customer_id: str
    outcome: ConsumerDutyOutcome
    rating: OutcomeRating
    interaction_type: str  # PAYMENT | KYC | COMPLAINT | SUPPORT | ONBOARDING
    notes: str = ""
    recorded_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ConsumerDutyReport:
    """
    Consumer Duty monitoring report for a period.
    PS22/9 §10: must be reviewed by the board at least annually.
    """

    period_start: date
    period_end: date
    generated_at: datetime

    total_customers: int
    vulnerable_customers: int

    # Outcome ratings: { outcome_area: { rating: count } }
    outcome_ratings: dict[str, dict[str, int]]

    # Fair value assessments per product
    fair_value_assessments: list[FairValueAssessment]

    complaints_count: int
    avg_complaint_resolution_days: float

    @property
    def vulnerable_pct(self) -> float:
        if self.total_customers == 0:
            return 0.0
        return round(self.vulnerable_customers / self.total_customers * 100, 1)

    @property
    def overall_good_outcome_pct(self) -> float:
        """Percentage of all outcome records rated GOOD."""
        total = 0
        good = 0
        for ratings in self.outcome_ratings.values():
            for rating, count in ratings.items():
                total += count
                if rating == OutcomeRating.GOOD.value:
                    good += count
        if total == 0:
            return 0.0
        return round(good / total * 100, 1)


# ── Port (protocol) ────────────────────────────────────────────────────────────


class ConsumerDutyPort(Protocol):
    """
    Hexagonal port for Consumer Duty obligations.
    Implementations: ConsumerDutyService (in-memory / ClickHouse).
    """

    def assess_vulnerability(
        self,
        customer_id: str,
        flags: list[VulnerabilityFlag],
        assessed_by: str,
        notes: str,
    ) -> VulnerabilityAssessment: ...

    def get_vulnerability(self, customer_id: str) -> VulnerabilityAssessment | None: ...

    def assess_fair_value(self, product_id: str, entity_type: str) -> FairValueAssessment: ...

    def record_outcome(
        self,
        customer_id: str,
        outcome: ConsumerDutyOutcome,
        rating: OutcomeRating,
        interaction_type: str,
        notes: str,
    ) -> OutcomeRecord: ...

    def generate_report(
        self,
        period_start: date,
        period_end: date,
        total_customers: int,
        complaints_count: int,
        avg_complaint_resolution_days: float,
    ) -> ConsumerDutyReport: ...
