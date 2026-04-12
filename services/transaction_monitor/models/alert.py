"""
services/transaction_monitor/models/alert.py — AML Alert models
IL-RTM-01 | banxe-emi-stack

AMLAlert: core alert entity with explanation and routing info.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from services.transaction_monitor.models.risk_score import RiskScore

# SLA: 24h for review, 4h for CRITICAL escalation
SLA_REVIEW_HOURS = 24
SLA_CRITICAL_HOURS = 4


class AlertSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    OPEN = "open"
    REVIEWING = "reviewing"
    ESCALATED = "escalated"
    CLOSED = "closed"
    AUTO_CLOSED = "auto_closed"


class AMLAlert(BaseModel):
    """AML alert with explainable risk factors and routing info."""

    alert_id: str = Field(default_factory=lambda: f"ALT-{uuid.uuid4().hex[:8].upper()}")
    transaction_id: str
    customer_id: str
    severity: AlertSeverity
    risk_score: RiskScore
    amount_gbp: Decimal = Field(..., description="Transaction amount in GBP (Decimal, I-01)")
    explanation: str = Field(default="", description="Human-readable summary for reviewer")
    regulation_refs: list[str] = Field(
        default_factory=list,
        description="KB citation IDs from Compliance KB (Part 1)",
    )
    recommended_action: str = Field(
        default="review",
        description="review | escalate | auto-close",
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    assigned_to: str | None = None
    marble_case_id: str | None = None
    status: AlertStatus = AlertStatus.OPEN
    review_deadline: datetime | None = None
    closed_at: datetime | None = None
    closure_reason: str | None = None
    audit_trail: list[dict[str, Any]] = Field(default_factory=list)

    def model_post_init(self, __context: object) -> None:
        """Set review deadline based on severity."""
        if self.review_deadline is None:
            hours = (
                SLA_CRITICAL_HOURS if self.severity == AlertSeverity.CRITICAL else SLA_REVIEW_HOURS
            )
            self.review_deadline = self.created_at + timedelta(hours=hours)


class AlertUpdateRequest(BaseModel):
    """Request to update an alert's status."""

    status: AlertStatus
    assigned_to: str | None = None
    closure_reason: str | None = None
    notes: str = ""


class BacktestRequest(BaseModel):
    """Request to backtest scoring rules on historical data."""

    from_date: datetime
    to_date: datetime
    rule_overrides: dict[str, Any] = Field(default_factory=dict)
    sample_size: int = Field(default=1000, ge=1, le=100000)


class BacktestResult(BaseModel):
    """Results from a backtest run."""

    from_date: datetime
    to_date: datetime
    total_transactions: int
    alerts_generated: int
    hit_rate: float  # nosemgrep: banxe-float-money — non-monetary rate
    false_positive_estimate: float  # nosemgrep: banxe-float-money — non-monetary rate
    sar_yield_estimate: float  # nosemgrep: banxe-float-money — non-monetary rate
    improvement_vs_baseline: float | None = (
        None  # nosemgrep: banxe-float-money — non-monetary delta
    )
    notes: str = ""
