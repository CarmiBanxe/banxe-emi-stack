"""
services/consumer_duty/outcome_assessor.py
Consumer Duty Outcome Assessor
IL-CDO-01 | Phase 50 | Sprint 35

FCA: PS22/9 Consumer Duty, FCA PRIN 12 (Consumer Principle)
Trust Zone: AMBER

assess_outcome — assesses one of 4 PS22/9 outcome areas.
get_failing_outcomes — outcomes below threshold.
aggregate_outcome_score — weighted average (Decimal, I-01).
Append-only (I-24). SHA-256 IDs. UTC timestamps.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import logging

from services.consumer_duty.models_v2 import (
    AssessmentStatus,
    InMemoryOutcomeStore,
    OutcomeAssessment,
    OutcomeStorePort,
    OutcomeType,
)

logger = logging.getLogger(__name__)

# I-01: All thresholds are Decimal
OUTCOME_THRESHOLDS: dict[OutcomeType, Decimal] = {
    OutcomeType.PRODUCTS_SERVICES: Decimal("0.7"),
    OutcomeType.PRICE_VALUE: Decimal("0.65"),
    OutcomeType.CONSUMER_UNDERSTANDING: Decimal("0.7"),
    OutcomeType.CONSUMER_SUPPORT: Decimal("0.75"),
}

# Weights for aggregate score (must sum to 1.0)
OUTCOME_WEIGHTS: dict[OutcomeType, Decimal] = {
    OutcomeType.PRODUCTS_SERVICES: Decimal("0.30"),
    OutcomeType.PRICE_VALUE: Decimal("0.25"),
    OutcomeType.CONSUMER_UNDERSTANDING: Decimal("0.20"),
    OutcomeType.CONSUMER_SUPPORT: Decimal("0.25"),
}


def _make_assessment_id(customer_id: str, outcome_type: str, ts: str) -> str:
    """Generate SHA-256-based assessment ID."""
    raw = f"{customer_id}:{outcome_type}:{ts}"
    return f"asm_{hashlib.sha256(raw.encode()).hexdigest()[:8]}"


def _extract_score(evidence_data: dict[str, object]) -> Decimal:
    """Extract and validate score from evidence data (I-01: Decimal)."""
    raw_score = evidence_data.get("score", Decimal("0.5"))
    score = Decimal(str(raw_score))
    # Clamp to 0.0–1.0
    if score < Decimal("0.0"):
        score = Decimal("0.0")
    if score > Decimal("1.0"):
        score = Decimal("1.0")
    return score


class OutcomeAssessor:
    """PS22/9 Consumer Duty outcome assessor.

    Protocol DI: OutcomeStorePort.
    I-01: All scores and thresholds use Decimal.
    I-24: Append-only outcome store.
    """

    def __init__(self, outcome_store: OutcomeStorePort | None = None) -> None:
        """Initialise with injectable outcome store (default: InMemory stub)."""
        self._store: OutcomeStorePort = outcome_store or InMemoryOutcomeStore()

    def assess_outcome(
        self,
        customer_id: str,
        outcome_type: OutcomeType,
        evidence_data: dict[str, object],
    ) -> OutcomeAssessment:
        """Assess a PS22/9 outcome area for a customer.

        Score < threshold → FAILED status.
        Score >= threshold → PASSED status.
        Appends to store (I-24).

        Args:
            customer_id: Customer identifier.
            outcome_type: One of the 4 PS22/9 outcome areas.
            evidence_data: Dict containing 'score' key (0.0–1.0).

        Returns:
            OutcomeAssessment (frozen dataclass).
        """
        ts = datetime.now(UTC).isoformat()
        score = _extract_score(evidence_data)
        threshold = OUTCOME_THRESHOLDS[outcome_type]

        status = AssessmentStatus.PASSED if score >= threshold else AssessmentStatus.FAILED

        if status == AssessmentStatus.FAILED:
            logger.warning(
                "Outcome FAILED customer=%s type=%s score=%s < threshold=%s",
                customer_id,
                outcome_type,
                score,
                threshold,
            )

        assessment_id = _make_assessment_id(customer_id, str(outcome_type), ts)
        evidence_str = str(evidence_data)

        assessment = OutcomeAssessment(
            assessment_id=assessment_id,
            customer_id=customer_id,
            outcome_type=outcome_type,
            score=score,
            status=status,
            assessed_at=ts,
            evidence=evidence_str,
        )
        self._store.append(assessment)  # I-24
        return assessment

    def get_customer_outcomes(self, customer_id: str) -> list[OutcomeAssessment]:
        """Get all outcome assessments for a customer.

        Args:
            customer_id: Customer identifier.

        Returns:
            List of OutcomeAssessment records.
        """
        return self._store.list_by_customer(customer_id)

    def get_failing_outcomes(
        self, outcome_type: OutcomeType | None = None
    ) -> list[OutcomeAssessment]:
        """Get all failed outcome assessments, optionally filtered by type.

        Args:
            outcome_type: Optional filter by outcome type.

        Returns:
            List of failed OutcomeAssessment records.
        """
        if outcome_type is not None:
            assessments = self._store.list_by_outcome_type(outcome_type)
        else:
            # Get all by iterating over all types
            assessments = []
            for ot in OutcomeType:
                assessments.extend(self._store.list_by_outcome_type(ot))

        return [a for a in assessments if a.status == AssessmentStatus.FAILED]

    def aggregate_outcome_score(self, customer_id: str) -> Decimal:
        """Calculate weighted aggregate outcome score for a customer (I-01: Decimal).

        Uses OUTCOME_WEIGHTS for weighted average.
        Returns 0.0 if no assessments found.

        Args:
            customer_id: Customer identifier.

        Returns:
            Weighted average score as Decimal (I-01).
        """
        assessments = self._store.list_by_customer(customer_id)
        if not assessments:
            return Decimal("0.0")

        # Latest per outcome type
        latest: dict[OutcomeType, OutcomeAssessment] = {}
        for a in assessments:
            latest[a.outcome_type] = a

        total_weight = Decimal("0.0")
        weighted_sum = Decimal("0.0")
        for outcome_type, assessment in latest.items():
            weight = OUTCOME_WEIGHTS.get(outcome_type, Decimal("0.25"))
            weighted_sum += assessment.score * weight
            total_weight += weight

        if total_weight == Decimal("0.0"):
            return Decimal("0.0")
        return weighted_sum / total_weight
