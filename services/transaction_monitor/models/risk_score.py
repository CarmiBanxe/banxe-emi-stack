"""
services/transaction_monitor/models/risk_score.py — Risk Score models
IL-RTM-01 | banxe-emi-stack

RiskFactor and RiskScore are non-monetary (scores/weights are floats 0-1).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

RiskClassification = Literal["low", "medium", "high", "critical"]

# Scoring thresholds
THRESHOLD_MEDIUM = 0.30
THRESHOLD_HIGH = 0.60
THRESHOLD_CRITICAL = 0.80


def classify_score(score: float) -> RiskClassification:
    """Classify a numeric score into a risk band."""
    if score >= THRESHOLD_CRITICAL:
        return "critical"
    if score >= THRESHOLD_HIGH:
        return "high"
    if score >= THRESHOLD_MEDIUM:
        return "medium"
    return "low"


class RiskFactor(BaseModel):
    """Single risk factor contributing to overall score.

    weight, value, contribution are non-monetary floats (rates/scores).
    """

    name: str = Field(..., description="e.g. 'velocity_24h', 'jurisdiction_risk'")
    weight: float = Field(
        ge=0.0, le=1.0, description="Factor weight in scoring"
    )  # nosemgrep: banxe-float-money — non-monetary weight
    value: float = Field(
        ..., description="Computed feature value"
    )  # nosemgrep: banxe-float-money — non-monetary feature
    contribution: float = Field(
        default=0.0, description="weight * normalised value"
    )  # nosemgrep: banxe-float-money — non-monetary
    explanation: str = Field(default="", description="Human-readable explanation")
    regulation_ref: str | None = Field(
        default=None,
        description="e.g. 'EBA GL 4.2.3', 'MLR 2017 Reg.33'",
    )


class RiskScore(BaseModel):
    """Composite risk score with factor breakdown.

    score is a non-monetary float 0–1 (I-01 does not apply to rates).
    """

    score: float = Field(ge=0.0, le=1.0)  # nosemgrep: banxe-float-money — non-monetary score
    classification: RiskClassification = "low"
    factors: list[RiskFactor] = Field(default_factory=list)
    model_version: str = "v1"
    computed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    rules_score: float = 0.0  # nosemgrep: banxe-float-money — non-monetary
    ml_score: float = 0.0  # nosemgrep: banxe-float-money — non-monetary
    velocity_score: float = 0.0  # nosemgrep: banxe-float-money — non-monetary

    def model_post_init(self, __context: object) -> None:
        self.classification = classify_score(self.score)
