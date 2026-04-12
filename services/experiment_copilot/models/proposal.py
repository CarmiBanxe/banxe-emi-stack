"""
services/experiment_copilot/models/proposal.py — Change proposal models
IL-CEC-01 | banxe-emi-stack

Models for Git PR/issue creation and HITL approval tracking.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ProposalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MERGED = "merged"


class HITLChecklist(BaseModel):
    """Human-in-the-loop approval checklist for every compliance change PR."""

    ctio_reviewed: bool = False
    compliance_officer_signoff: bool = False
    backtest_results_reviewed: bool = False
    rollback_plan_defined: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    approved_at: datetime | None = None
    approved_by: str | None = None

    @property
    def is_complete(self) -> bool:
        return all(
            [
                self.ctio_reviewed,
                self.compliance_officer_signoff,
                self.backtest_results_reviewed,
                self.rollback_plan_defined,
            ]
        )

    @property
    def missing_items(self) -> list[str]:
        missing = []
        if not self.ctio_reviewed:
            missing.append("CTIO review")
        if not self.compliance_officer_signoff:
            missing.append("Compliance officer sign-off")
        if not self.backtest_results_reviewed:
            missing.append("Backtest results review")
        if not self.rollback_plan_defined:
            missing.append("Rollback plan")
        return missing


class ChangeProposal(BaseModel):
    """A proposed change derived from an approved experiment."""

    experiment_id: str
    branch_name: str
    pr_title: str
    pr_body: str
    pr_url: str | None = None
    issue_url: str | None = None
    status: ProposalStatus = ProposalStatus.PENDING
    hitl_checklist: HITLChecklist = Field(default_factory=HITLChecklist)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    files_changed: list[str] = Field(default_factory=list)


class ProposeRequest(BaseModel):
    """Request to create a PR for an experiment."""

    experiment_id: str | None = Field(
        default=None,
        description="Experiment ID — optional when passed as URL path parameter",
    )
    dry_run: bool = Field(
        default=True,
        description="If True, generate PR body but do not create branch/PR",
    )
