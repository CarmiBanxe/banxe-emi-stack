"""
services/experiment_copilot/models/metrics.py — AML metrics models
IL-CEC-01 | banxe-emi-stack

Performance metrics for AML/KYC compliance experiments.
Rates and percentages use float (non-monetary).
GBP amounts use Decimal (I-01).
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MetricTrend(str, Enum):
    IMPROVING = "improving"
    REGRESSING = "regressing"
    INCONCLUSIVE = "inconclusive"
    UNCHANGED = "unchanged"


class ExperimentMetrics(BaseModel):
    """AML performance metrics snapshot.

    Note: hit_rate_*, false_positive_rate, sar_yield are dimensionless ratios [0.0, 1.0].
    These are NOT monetary values — float precision is sufficient.
    amount_blocked_gbp uses Decimal (monetary amount, I-01).
    """

    # Rates [0.0, 1.0] — not monetary, float is correct
    hit_rate_24h: float | None = Field(
        default=None, description="Alert hit rate in 24h window (target >60%)"
    )
    false_positive_rate: float | None = Field(
        default=None, description="False positive rate (target <30%)"
    )
    sar_yield: float | None = Field(default=None, description="SAR conversion rate (target >20%)")

    # Duration — not monetary
    time_to_review_hours: float | None = Field(
        default=None, description="Mean time to review an alert in hours"
    )

    # Monetary — Decimal (I-01)
    amount_blocked_gbp: Decimal | None = Field(
        default=None, description="GBP value of transactions blocked"
    )

    # Counts
    cases_reviewed: int = 0
    period_days: int = 0


class MetricsComparison(BaseModel):
    """Comparison of actual metrics vs baseline and target."""

    experiment_id: str
    period_days: int
    baseline: dict[str, Any]
    target: dict[str, Any]
    actual: ExperimentMetrics
    trend: MetricTrend
    improvement_pct: float | None = None
    narrative: str = ""
    recommendation: str = ""  # "continue" | "stop" | "extend"


class AMLBaselines(BaseModel):
    """AML performance baselines loaded from config/aml_baselines.yaml."""

    hit_rate_24h_current: float
    hit_rate_24h_target: float
    review_sla_current_pct: float
    review_sla_target_pct: float
    false_positive_rate_current: float
    false_positive_rate_target: float
    sar_yield_current: float
    sar_yield_target: float
    coverage_gaps: list[dict[str, str]] = Field(default_factory=list)
