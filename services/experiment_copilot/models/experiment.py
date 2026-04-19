"""
services/experiment_copilot/models/experiment.py — Experiment Pydantic models
IL-CEC-01 | banxe-emi-stack

ComplianceExperiment: core entity for AML/KYC rule change experiments.
Persisted as YAML in compliance-experiments/{draft|active|finished|rejected}/.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ExperimentStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    FINISHED = "finished"
    REJECTED = "rejected"


class ExperimentScope(str, Enum):
    TRANSACTION_MONITORING = "transaction_monitoring"
    KYC_ONBOARDING = "kyc_onboarding"
    CASE_MANAGEMENT = "case_management"
    SAR_FILING = "sar_filing"
    RISK_SCORING = "risk_scoring"


class ComplianceExperiment(BaseModel):
    id: str = Field(..., description="e.g. 'exp-2026-04-velocity-p2p'")
    title: str
    scope: ExperimentScope
    status: ExperimentStatus = ExperimentStatus.DRAFT
    hypothesis: str = Field(..., description="What we expect to improve and why")
    kb_citations: list[str] = Field(
        default_factory=list,
        description="Citation IDs from the Compliance KB (Part 1)",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str = Field(default="claude-code", description="'claude-code' | 'human'")
    metrics_baseline: dict[str, Any] = Field(default_factory=dict)
    metrics_target: dict[str, Any] = Field(default_factory=dict)
    metrics_actual: dict[str, Any] = Field(default_factory=dict)
    pr_url: str | None = None
    issue_url: str | None = None
    audit_entries: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    rejection_reason: str | None = None
    steward_notes: str | None = None


class ExperimentSummary(BaseModel):
    """Lightweight experiment summary for list views."""

    id: str
    title: str
    scope: ExperimentScope
    status: ExperimentStatus
    created_at: datetime
    updated_at: datetime
    created_by: str
    tags: list[str] = Field(default_factory=list)
    has_pr: bool = False

    @classmethod
    def from_experiment(cls, exp: ComplianceExperiment) -> ExperimentSummary:
        return cls(
            id=exp.id,
            title=exp.title,
            scope=exp.scope,
            status=exp.status,
            created_at=exp.created_at,
            updated_at=exp.updated_at,
            created_by=exp.created_by,
            tags=exp.tags,
            has_pr=exp.pr_url is not None,
        )


class ApproveRequest(BaseModel):
    steward_notes: str | None = None


class RejectRequest(BaseModel):
    reason: str = Field(..., min_length=10)


class DesignRequest(BaseModel):
    query: str = Field(..., description="KB query, e.g. 'velocity limits for P2P EMI'")
    scope: ExperimentScope
    created_by: str = "claude-code"
    tags: list[str] = Field(default_factory=list)
