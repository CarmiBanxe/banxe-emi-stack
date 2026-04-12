"""
tests/test_experiment_copilot/test_change_proposer.py
IL-CEC-01 | banxe-emi-stack

Tests for ChangeProposer: dry_run mode, PR/issue creation (InMemoryGitHubPort),
HITL checklist generation, and branch naming.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from services.experiment_copilot.agents.change_proposer import (
    ChangeProposer,
    InMemoryGitHubPort,
)
from services.experiment_copilot.models.experiment import (
    ComplianceExperiment,
    ExperimentScope,
    ExperimentStatus,
)
from services.experiment_copilot.models.proposal import (
    ProposalStatus,
    ProposeRequest,
)
from services.experiment_copilot.store.audit_trail import AuditTrail


def _make_active_experiment(exp_id: str = "exp-2026-04-prop-test") -> ComplianceExperiment:
    return ComplianceExperiment(
        id=exp_id,
        title="Velocity Control Tuning",
        scope=ExperimentScope.TRANSACTION_MONITORING,
        status=ExperimentStatus.ACTIVE,
        hypothesis="By tuning velocity controls, we expect to reduce false positives by 15%.",
        kb_citations=["eba-gl-2021-02", "fatf-rec-10"],
        created_by="compliance@banxe.com",
        metrics_baseline={"hit_rate_24h": 0.25, "false_positive_rate": 0.75},
        metrics_target={"hit_rate_24h": 0.35, "false_positive_rate": 0.60},
    )


def _make_proposer(tmp_path: Path) -> tuple[ChangeProposer, InMemoryGitHubPort]:
    audit = AuditTrail(log_path=str(tmp_path / "audit.jsonl"))
    github = InMemoryGitHubPort()
    proposer = ChangeProposer(audit=audit, github=github, repo_root=str(tmp_path))
    return proposer, github


class TestDryRunPropose:
    def test_dry_run_returns_pending_proposal(self, tmp_path):
        proposer, github = _make_proposer(tmp_path)
        exp = _make_active_experiment()
        proposal = proposer.propose(exp, ProposeRequest(dry_run=True))
        assert proposal.status == ProposalStatus.PENDING
        assert proposal.experiment_id == exp.id

    def test_dry_run_does_not_create_pr(self, tmp_path):
        proposer, github = _make_proposer(tmp_path)
        exp = _make_active_experiment()
        proposer.propose(exp, ProposeRequest(dry_run=True))
        assert len(github.prs_created) == 0

    def test_dry_run_sets_branch_name(self, tmp_path):
        proposer, _ = _make_proposer(tmp_path)
        exp = _make_active_experiment("exp-branch-test")
        proposal = proposer.propose(exp, ProposeRequest(dry_run=True))
        assert proposal.branch_name == "compliance/exp-exp-branch-test"

    def test_dry_run_pr_body_includes_hypothesis(self, tmp_path):
        proposer, _ = _make_proposer(tmp_path)
        exp = _make_active_experiment()
        proposal = proposer.propose(exp, ProposeRequest(dry_run=True))
        assert "velocity controls" in proposal.pr_body.lower()

    def test_dry_run_pr_body_includes_hitl_checklist(self, tmp_path):
        proposer, _ = _make_proposer(tmp_path)
        exp = _make_active_experiment()
        proposal = proposer.propose(exp, ProposeRequest(dry_run=True))
        assert "[ ]" in proposal.pr_body

    def test_propose_non_active_raises_value_error(self, tmp_path):
        proposer, _ = _make_proposer(tmp_path)
        exp = _make_active_experiment()
        exp.status = ExperimentStatus.DRAFT
        with pytest.raises(ValueError, match="ACTIVE"):
            proposer.propose(exp, ProposeRequest(dry_run=True))
